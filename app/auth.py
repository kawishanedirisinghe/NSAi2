from flask import Blueprint, request, jsonify, session, current_app
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import uuid
import secrets
from functools import wraps
import re

from .models import db, User, UserSession, SystemLog, UserRole, UserStatus

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# Initialize Flask-Login
login_manager = LoginManager()

@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login"""
    return User.query.get(user_id)

def log_security_event(level, message, user_id=None, metadata=None):
    """Log security events"""
    try:
        log_entry = SystemLog(
            level=level,
            category='auth',
            message=message,
            user_id=user_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            metadata=metadata or {}
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Failed to log security event: {e}")

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"
    
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character"
    
    return True, "Password is valid"

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            return jsonify({'error': 'Admin privileges required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def active_user_required(f):
    """Decorator to require active user status"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_active_user():
            return jsonify({'error': 'Active user account required'}), 403
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/register', methods=['POST'])
def register():
    """User registration endpoint"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['username', 'email', 'password', 'full_name']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        username = data['username'].strip().lower()
        email = data['email'].strip().lower()
        password = data['password']
        full_name = data['full_name'].strip()
        
        # Validate input
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        is_valid, password_message = validate_password(password)
        if not is_valid:
            return jsonify({'error': password_message}), 400
        
        if len(username) < 3 or len(username) > 20:
            return jsonify({'error': 'Username must be 3-20 characters long'}), 400
        
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return jsonify({'error': 'Username can only contain letters, numbers, and underscores'}), 400
        
        # Check if user already exists
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 400
        
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already registered'}), 400
        
        # Create new user
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            role=UserRole.USER,
            status=UserStatus.ACTIVE
        )
        user.set_password(password)
        
        # Set first user as admin
        if User.query.count() == 0:
            user.role = UserRole.ADMIN
        
        db.session.add(user)
        db.session.commit()
        
        log_security_event('INFO', f'New user registered: {username}', user.id)
        
        return jsonify({
            'message': 'Registration successful',
            'user': user.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Registration error: {e}")
        return jsonify({'error': 'Registration failed'}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    """User login endpoint"""
    try:
        data = request.get_json()
        
        username_or_email = data.get('username', '').strip().lower()
        password = data.get('password', '')
        
        if not username_or_email or not password:
            return jsonify({'error': 'Username/email and password are required'}), 400
        
        # Find user by username or email
        user = User.query.filter(
            (User.username == username_or_email) | 
            (User.email == username_or_email)
        ).first()
        
        if not user or not user.check_password(password):
            log_security_event('WARNING', f'Failed login attempt for: {username_or_email}', 
                             user.id if user else None)
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not user.is_active_user():
            log_security_event('WARNING', f'Login attempt for inactive user: {username_or_email}', user.id)
            return jsonify({'error': 'Account is inactive or suspended'}), 403
        
        # Update last login
        user.last_login = datetime.utcnow()
        
        # Create session
        session_token = secrets.token_urlsafe(32)
        user_session = UserSession(
            user_id=user.id,
            session_token=session_token,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        
        db.session.add(user_session)
        db.session.commit()
        
        # Login user with Flask-Login
        login_user(user, remember=True)
        
        log_security_event('INFO', f'User logged in: {user.username}', user.id)
        
        return jsonify({
            'message': 'Login successful',
            'user': user.to_dict(),
            'session_token': session_token
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """User logout endpoint"""
    try:
        # Deactivate current session
        session_token = request.headers.get('X-Session-Token')
        if session_token:
            user_session = UserSession.query.filter_by(
                session_token=session_token,
                user_id=current_user.id
            ).first()
            if user_session:
                user_session.is_active = False
                db.session.commit()
        
        log_security_event('INFO', f'User logged out: {current_user.username}', current_user.id)
        
        logout_user()
        
        return jsonify({'message': 'Logout successful'}), 200
        
    except Exception as e:
        current_app.logger.error(f"Logout error: {e}")
        return jsonify({'error': 'Logout failed'}), 500

@auth_bp.route('/profile', methods=['GET'])
@login_required
@active_user_required
def get_profile():
    """Get current user profile"""
    return jsonify({
        'user': current_user.to_dict()
    }), 200

@auth_bp.route('/profile', methods=['PUT'])
@login_required
@active_user_required
def update_profile():
    """Update user profile"""
    try:
        data = request.get_json()
        
        # Update allowed fields
        allowed_fields = ['full_name', 'bio', 'avatar_url']
        for field in allowed_fields:
            if field in data:
                setattr(current_user, field, data[field])
        
        # Update preferences
        if 'preferences' in data:
            current_user.preferences = {**current_user.preferences, **data['preferences']}
        
        current_user.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': 'Profile updated successfully',
            'user': current_user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Profile update error: {e}")
        return jsonify({'error': 'Profile update failed'}), 500

@auth_bp.route('/change-password', methods=['POST'])
@login_required
@active_user_required
def change_password():
    """Change user password"""
    try:
        data = request.get_json()
        
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not current_password or not new_password:
            return jsonify({'error': 'Current and new passwords are required'}), 400
        
        if not current_user.check_password(current_password):
            return jsonify({'error': 'Current password is incorrect'}), 400
        
        is_valid, password_message = validate_password(new_password)
        if not is_valid:
            return jsonify({'error': password_message}), 400
        
        current_user.set_password(new_password)
        current_user.updated_at = datetime.utcnow()
        
        # Deactivate all other sessions
        UserSession.query.filter_by(user_id=current_user.id).update({'is_active': False})
        
        db.session.commit()
        
        log_security_event('INFO', f'Password changed for user: {current_user.username}', current_user.id)
        
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Password change error: {e}")
        return jsonify({'error': 'Password change failed'}), 500

@auth_bp.route('/sessions', methods=['GET'])
@login_required
@active_user_required
def get_sessions():
    """Get user's active sessions"""
    try:
        sessions = UserSession.query.filter_by(
            user_id=current_user.id,
            is_active=True
        ).filter(UserSession.expires_at > datetime.utcnow()).all()
        
        session_list = []
        for s in sessions:
            session_list.append({
                'id': s.id,
                'created_at': s.created_at.isoformat(),
                'expires_at': s.expires_at.isoformat(),
                'ip_address': s.ip_address,
                'user_agent': s.user_agent[:100] + '...' if len(s.user_agent) > 100 else s.user_agent
            })
        
        return jsonify({'sessions': session_list}), 200
        
    except Exception as e:
        current_app.logger.error(f"Get sessions error: {e}")
        return jsonify({'error': 'Failed to get sessions'}), 500

@auth_bp.route('/sessions/<session_id>', methods=['DELETE'])
@login_required
@active_user_required
def revoke_session(session_id):
    """Revoke a specific session"""
    try:
        user_session = UserSession.query.filter_by(
            id=session_id,
            user_id=current_user.id
        ).first()
        
        if not user_session:
            return jsonify({'error': 'Session not found'}), 404
        
        user_session.is_active = False
        db.session.commit()
        
        return jsonify({'message': 'Session revoked successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Session revoke error: {e}")
        return jsonify({'error': 'Failed to revoke session'}), 500

@auth_bp.route('/verify-token', methods=['POST'])
def verify_token():
    """Verify session token"""
    try:
        data = request.get_json()
        token = data.get('token')
        
        if not token:
            return jsonify({'valid': False, 'error': 'Token required'}), 400
        
        user_session = UserSession.query.filter_by(
            session_token=token,
            is_active=True
        ).first()
        
        if not user_session or user_session.is_expired():
            return jsonify({'valid': False, 'error': 'Invalid or expired token'}), 401
        
        user = User.query.get(user_session.user_id)
        if not user or not user.is_active_user():
            return jsonify({'valid': False, 'error': 'User account inactive'}), 401
        
        # Extend session
        user_session.extend_session()
        db.session.commit()
        
        return jsonify({
            'valid': True,
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Token verification error: {e}")
        return jsonify({'valid': False, 'error': 'Token verification failed'}), 500