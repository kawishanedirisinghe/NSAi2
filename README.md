# OpenManus AI - Enhanced Multi-User Platform

🚀 **Advanced AI Platform with Multi-User Support, VM Optimization, and Real-Time Collaboration**

OpenManus AI is a comprehensive, production-ready AI platform designed for multi-user environments, VM deployments, and enterprise use. It features advanced user management, real-time WebSocket communication, VM resource monitoring, and AI model optimization.

## ✨ Key Features

### 🔐 **Multi-User Authentication & Authorization**
- Secure user registration and login system
- Role-based access control (Admin, Moderator, User)
- Session management with token-based authentication
- Password strength validation and security logging

### 💬 **Real-Time Multi-User Chat**
- WebSocket-based real-time communication
- Public and private chat rooms
- Room management and user permissions
- Typing indicators and user presence
- Message history and persistence

### 🖥️ **VM Resource Management**
- Real-time CPU, Memory, and GPU monitoring
- Automated resource alerting and thresholds
- VM optimization recommendations
- Auto-scaling capabilities
- Performance metrics and analytics

### 🤖 **AI Model Integration**
- Multi-model support and management
- Resource-aware model loading
- Request tracking and performance monitoring
- GPU utilization optimization
- Model lifecycle management

### 📊 **Advanced Monitoring & Analytics**
- System health monitoring
- Resource usage analytics
- User activity tracking
- Performance metrics dashboard
- Prometheus and Grafana integration

### 🐳 **Production-Ready Deployment**
- Docker containerization
- Multi-stage builds for optimization
- PostgreSQL database with migrations
- Redis for caching and sessions
- NGINX reverse proxy support
- SSL/TLS encryption ready

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.11+ (for local development)
- Git
- 4GB+ RAM recommended
- NVIDIA GPU (optional, for AI acceleration)

### One-Command Installation

```bash
# Clone the repository
git clone https://github.com/your-org/openmanus-ai.git
cd openmanus-ai

# Run the interactive installer
./deploy.sh
```

The deployment script will:
1. Detect your system configuration
2. Install required dependencies
3. Set up Docker and containers
4. Configure the database
5. Start all services
6. Optionally set up monitoring

### Manual Installation

```bash
# 1. Clone and setup
git clone https://github.com/your-org/openmanus-ai.git
cd openmanus-ai

# 2. Configure environment
cp .env.example .env
# Edit .env with your settings

# 3. Start services
docker-compose up -d

# 4. Access the application
open http://localhost:5000
```

## 📖 Usage Guide

### Default Admin Account
- **Username**: `admin`
- **Password**: `admin123` (change immediately!)
- **Email**: `admin@openmanus.ai`

### API Endpoints

#### Authentication
```bash
# Register new user
POST /api/auth/register
{
  "username": "newuser",
  "email": "user@example.com",
  "password": "SecurePass123!",
  "full_name": "New User"
}

# Login
POST /api/auth/login
{
  "username": "admin",
  "password": "admin123"
}
```

#### System Monitoring
```bash
# System health
GET /api/system/health

# Current metrics
GET /api/system/metrics

# Metrics history
GET /api/system/metrics/history?hours=24

# System alerts
GET /api/system/alerts

# Optimization recommendations
GET /api/system/optimize
```

#### Chat Rooms
```bash
# Get available rooms
GET /api/rooms

# Create new room
POST /api/rooms
{
  "name": "Development Team",
  "description": "Team collaboration space",
  "is_public": true
}
```

### WebSocket Connection

```javascript
// Connect to WebSocket
const socket = io('http://localhost:5000', {
  auth: {
    token: 'your-session-token'
  }
});

// Join a room
socket.emit('join_room', { room_id: 'room-uuid' });

// Send message
socket.emit('send_message', {
  room_id: 'room-uuid',
  content: 'Hello everyone!',
  type: 'text'
});

// Listen for messages
socket.on('new_message', (data) => {
  console.log('New message:', data);
});
```

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   NGINX Proxy   │───▶│  Flask App      │───▶│   PostgreSQL    │
│   (Port 80/443) │    │  (Port 5000)    │    │   (Port 5432)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                               │
                       ┌───────┴───────┐
                       ▼               ▼
                ┌─────────────┐ ┌─────────────┐
                │    Redis    │ │  WebSocket  │
                │ (Port 6379) │ │   Manager   │
                └─────────────┘ └─────────────┘
```

### Core Components

- **Flask Application**: Main web server with REST API
- **PostgreSQL**: Primary database for user data and chat history
- **Redis**: Session storage and caching
- **WebSocket Manager**: Real-time communication handling
- **VM Resource Manager**: System monitoring and optimization
- **Authentication System**: Secure user management

## 🛠️ Development

### Local Development Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set up database
export DATABASE_URL=sqlite:///openmanus.db
python -c "from main import initialize_database; initialize_database()"

# Run development server
python main.py
```

### Development with Docker

```bash
# Start development environment
docker-compose --profile development up -d openmanus-dev

# View logs
docker-compose logs -f openmanus-dev
```

### Database Migrations

```bash
# Generate migration
flask db migrate -m "Description of changes"

# Apply migrations
flask db upgrade
```

### Testing

```bash
# Run tests
python -m pytest tests/

# Run with coverage
python -m pytest --cov=app tests/
```

## 📊 Monitoring & Observability

### Built-in Monitoring

Access the monitoring dashboard at `/api/system/health` to view:
- CPU, Memory, and GPU utilization
- Active user sessions
- WebSocket connections
- AI model status
- System alerts and recommendations

### External Monitoring (Optional)

Enable Prometheus and Grafana for advanced monitoring:

```bash
# Start monitoring services
docker-compose --profile monitoring up -d

# Access Grafana
open http://localhost:3000
# Username: admin, Password: admin123
```

## 🔧 Configuration

### Environment Variables

Key configuration options in `.env`:

```env
# Security
SECRET_KEY=your-secret-key
HTTPS=false

# Database
DATABASE_URL=postgresql://user:pass@host:port/db

# VM Monitoring
VM_CPU_THRESHOLD=80.0
VM_MEMORY_THRESHOLD=85.0
VM_AUTO_SCALING=true

# WebSocket
WS_PING_TIMEOUT=60
WS_PING_INTERVAL=25
```

### Resource Limits

Adjust Docker resource limits in `docker-compose.yml`:

```yaml
deploy:
  resources:
    limits:
      memory: 4G
      cpus: '2.0'
    reservations:
      memory: 2G
      cpus: '1.0'
```

## 🚀 Deployment Options

### VM Deployment

```bash
# One-command deployment
./deploy.sh install

# Or step by step
./deploy.sh start
./deploy.sh monitoring
./deploy.sh status
```

### Cloud Deployment

#### AWS EC2
```bash
# Launch EC2 instance (Ubuntu 22.04 LTS)
# Recommended: t3.large or larger with 4GB+ RAM

# SSH into instance and run
git clone https://github.com/your-org/openmanus-ai.git
cd openmanus-ai
./deploy.sh install
```

#### Google Cloud Platform
```bash
# Create VM instance
gcloud compute instances create openmanus-ai \
  --machine-type=e2-standard-2 \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud

# Deploy application
./deploy.sh install
```

#### Docker Swarm
```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml openmanus
```

### Kubernetes Deployment

```bash
# Apply Kubernetes manifests
kubectl apply -f k8s/
```

## 🔐 Security Features

- **Password Security**: Enforced strong passwords with complexity requirements
- **Session Management**: Secure token-based sessions with expiration
- **Input Validation**: Comprehensive input sanitization and validation
- **Rate Limiting**: Configurable rate limits for API endpoints
- **CORS Protection**: Configurable CORS policies
- **SQL Injection Prevention**: Parameterized queries and ORM usage
- **XSS Protection**: Input sanitization and CSP headers
- **Secure Headers**: Security headers for production deployment

## 📈 Performance Optimization

### Database Optimization
- Connection pooling
- Query optimization with indexes
- Automatic vacuum and maintenance

### Caching Strategy
- Redis for session storage
- Application-level caching for frequently accessed data
- Static asset caching with NGINX

### Resource Management
- Automatic resource monitoring
- Smart model loading based on usage
- Memory cleanup and garbage collection

## 🐛 Troubleshooting

### Common Issues

#### Application won't start
```bash
# Check logs
docker-compose logs openmanus

# Verify database connection
docker-compose exec postgres pg_isready -U openmanus

# Reset and restart
docker-compose down && docker-compose up -d
```

#### WebSocket connection issues
```bash
# Check if port 5000 is accessible
curl http://localhost:5000/api/system/health

# Verify WebSocket endpoint
curl -H "Connection: Upgrade" -H "Upgrade: websocket" http://localhost:5000/socket.io/
```

#### High resource usage
```bash
# Check system metrics
curl http://localhost:5000/api/system/metrics

# View optimization recommendations
curl http://localhost:5000/api/system/optimize
```

### Support

- **Documentation**: Check the `/docs` endpoint for API documentation
- **Logs**: View application logs with `docker-compose logs -f openmanus`
- **Health Check**: Monitor system health at `/api/system/health`
- **Issues**: Report issues on the GitHub repository

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Flask and the Python ecosystem
- Docker and containerization technologies
- WebSocket.IO for real-time communication
- PostgreSQL for reliable data storage
- The open-source community

---

**OpenManus AI** - Empowering multi-user AI collaboration with enterprise-grade features and VM optimization.

For more information, visit our [documentation](https://docs.openmanus.ai) or join our [community](https://community.openmanus.ai).