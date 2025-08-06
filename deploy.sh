#!/bin/bash

# OpenManus AI Platform Deployment Script
# Supports VM, Docker, and cloud deployment

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="openmanus-ai"
BACKUP_DIR="backups"
LOG_FILE="deployment.log"

# Functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" | tee -a "$LOG_FILE"
    exit 1
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}" | tee -a "$LOG_FILE"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        warn "Running as root. Consider using a non-root user for security."
    fi
}

# Detect system information
detect_system() {
    log "Detecting system information..."
    
    # OS Detection
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        if command -v lsb_release &> /dev/null; then
            DISTRO=$(lsb_release -si)
            VERSION=$(lsb_release -sr)
        elif [ -f /etc/os-release ]; then
            . /etc/os-release
            DISTRO=$NAME
            VERSION=$VERSION_ID
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        DISTRO="macOS"
        VERSION=$(sw_vers -productVersion)
    else
        error "Unsupported operating system: $OSTYPE"
    fi
    
    # Architecture
    ARCH=$(uname -m)
    
    # Memory
    if [[ "$OS" == "linux" ]]; then
        MEMORY_GB=$(($(grep MemTotal /proc/meminfo | awk '{print $2}') / 1024 / 1024))
    elif [[ "$OS" == "macos" ]]; then
        MEMORY_GB=$(($(sysctl -n hw.memsize) / 1024 / 1024 / 1024))
    fi
    
    # CPU cores
    CPU_CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo "unknown")
    
    log "System Information:"
    log "  OS: $DISTRO $VERSION ($ARCH)"
    log "  Memory: ${MEMORY_GB}GB"
    log "  CPU Cores: $CPU_CORES"
}

# Install system dependencies
install_dependencies() {
    log "Installing system dependencies..."
    
    if [[ "$OS" == "linux" ]]; then
        # Update package manager
        if command -v apt-get &> /dev/null; then
            sudo apt-get update
            sudo apt-get install -y curl wget git build-essential python3 python3-pip python3-venv
        elif command -v yum &> /dev/null; then
            sudo yum update -y
            sudo yum install -y curl wget git gcc gcc-c++ python3 python3-pip python3-venv
        elif command -v dnf &> /dev/null; then
            sudo dnf update -y
            sudo dnf install -y curl wget git gcc gcc-c++ python3 python3-pip python3-venv
        else
            error "Unsupported package manager. Please install dependencies manually."
        fi
    elif [[ "$OS" == "macos" ]]; then
        # Check if Homebrew is installed
        if ! command -v brew &> /dev/null; then
            log "Installing Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi
        brew install python3 git curl wget
    fi
}

# Install Docker
install_docker() {
    if command -v docker &> /dev/null; then
        log "Docker is already installed"
        return
    fi
    
    log "Installing Docker..."
    
    if [[ "$OS" == "linux" ]]; then
        # Install Docker using official script
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        sudo usermod -aG docker $USER
        
        # Install Docker Compose
        sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
        
        # Start Docker service
        sudo systemctl start docker
        sudo systemctl enable docker
        
    elif [[ "$OS" == "macos" ]]; then
        warn "Please install Docker Desktop for Mac manually from https://docker.com"
        read -p "Press Enter after installing Docker Desktop..."
    fi
    
    # Verify Docker installation
    if ! docker --version &> /dev/null; then
        error "Docker installation failed"
    fi
    
    log "Docker installed successfully"
}



# Setup environment
setup_environment() {
    log "Setting up environment..."
    
    # Create necessary directories
    mkdir -p workspace uploads logs backups config
    
    # Copy environment file if it doesn't exist
    if [[ ! -f .env ]]; then
        if [[ -f .env.example ]]; then
            cp .env.example .env
            log "Created .env file from .env.example"
            warn "Please edit .env file with your configuration"
        else
            error ".env.example file not found"
        fi
    fi
    
    # Generate secret key if needed
    if grep -q "your-super-secret-key-change-this-in-production" .env; then
        SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
        sed -i "s/your-super-secret-key-change-this-in-production/$SECRET_KEY/" .env
        log "Generated new secret key"
    fi
    
    # Set appropriate permissions
    chmod 600 .env
    chmod +x deploy.sh
}

# Build and start services
start_services() {
    log "Building and starting services..."
    
    # Build Docker images
    docker-compose build
    
    # Start core services
    docker-compose up -d postgres redis
    
    # Wait for database to be ready
    log "Waiting for database to be ready..."
    for i in {1..30}; do
        if docker-compose exec -T postgres pg_isready -U openmanus &> /dev/null; then
            log "Database is ready"
            break
        fi
        if [[ $i -eq 30 ]]; then
            error "Database failed to start within 30 seconds"
        fi
        sleep 1
    done
    
    # Start main application
    docker-compose up -d openmanus
    
    # Wait for application to be ready
    log "Waiting for application to be ready..."
    for i in {1..60}; do
        if curl -f http://localhost:5000/api/system/health &> /dev/null; then
            log "Application is ready"
            break
        fi
        if [[ $i -eq 60 ]]; then
            error "Application failed to start within 60 seconds"
        fi
        sleep 1
    done
}



# Create backup
create_backup() {
    log "Creating backup..."
    
    BACKUP_NAME="${PROJECT_NAME}-backup-$(date +%Y%m%d-%H%M%S)"
    BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"
    
    mkdir -p "$BACKUP_PATH"
    
    # Backup database
    docker-compose exec -T postgres pg_dump -U openmanus openmanus > "$BACKUP_PATH/database.sql"
    
    # Backup application data
    cp -r workspace "$BACKUP_PATH/"
    cp -r uploads "$BACKUP_PATH/"
    cp -r config "$BACKUP_PATH/"
    cp .env "$BACKUP_PATH/"
    
    # Create archive
    tar -czf "$BACKUP_PATH.tar.gz" -C "$BACKUP_DIR" "$BACKUP_NAME"
    rm -rf "$BACKUP_PATH"
    
    log "Backup created: $BACKUP_PATH.tar.gz"
}

# Show status
show_status() {
    log "System Status:"
    
    # Docker services
    echo "Docker Services:"
    docker-compose ps
    
    # Application health
    echo -e "\nApplication Health:"
    if curl -f http://localhost:5000/api/system/health 2>/dev/null; then
        echo "✅ Application is healthy"
    else
        echo "❌ Application is not responding"
    fi
    
    # System resources
    echo -e "\nSystem Resources:"
    if command -v docker &> /dev/null; then
        docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
    fi
}

# Cleanup function
cleanup() {
    log "Cleaning up..."
    docker-compose down
    docker system prune -f
}

# Update function
update() {
    log "Updating OpenManus AI Platform..."
    
    # Create backup before update
    create_backup
    
    # Pull latest changes
    git pull origin main
    
    # Rebuild and restart services
    docker-compose down
    docker-compose build --no-cache
    start_services
    
    log "Update completed successfully"
}

# Main menu
show_menu() {
    echo -e "\n${BLUE}OpenManus AI Platform Deployment${NC}"
    echo "=================================="
    echo "1. Full Installation"
    echo "2. Start Services"
    echo "3. Stop Services"
    echo "4. Show Status"
    echo "5. Create Backup"
    echo "6. Update Platform"
    echo "7. Cleanup"
    echo "8. Exit"
    echo
}

# Main execution
main() {
    log "Starting OpenManus AI Platform Deployment"
    
    # Check prerequisites
    check_root
    detect_system
    
    if [[ $# -eq 0 ]]; then
        # Interactive mode
        while true; do
            show_menu
            read -p "Select an option [1-8]: " choice
            
            case $choice in
                1)
                    install_dependencies
                    install_docker
                    setup_environment
                    start_services
                    show_status
                    ;;
                2)
                    start_services
                    ;;
                3)
                    docker-compose down
                    ;;
                4)
                    show_status
                    ;;
                5)
                    create_backup
                    ;;
                6)
                    update
                    ;;
                7)
                    cleanup
                    ;;
                8)
                    log "Goodbye!"
                    exit 0
                    ;;
                *)
                    warn "Invalid option. Please try again."
                    ;;
            esac
            
            echo
            read -p "Press Enter to continue..."
        done
    else
        # Command line mode
        case $1 in
            install)
                install_dependencies
                install_docker
                setup_environment
                start_services
                ;;
            start)
                start_services
                ;;
            stop)
                docker-compose down
                ;;
            status)
                show_status
                ;;
            backup)
                create_backup
                ;;
            update)
                update
                ;;
            cleanup)
                cleanup
                ;;
            *)
                echo "Usage: $0 [install|start|stop|status|backup|update|cleanup]"
                exit 1
                ;;
        esac
    fi
}

# Run main function
main "$@"