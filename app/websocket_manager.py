from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect
from flask_login import current_user
from flask import request, current_app
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional
import logging
from functools import wraps

from .models import db, User, ChatRoom, ChatMessage, UserRoom, SystemLog
from .auth import log_security_event

class WebSocketManager:
    def __init__(self, app=None):
        self.socketio = None
        self.active_connections = {}  # {session_id: {user_id, rooms, socket_id}}
        self.room_users = {}  # {room_id: set(user_ids)}
        self.user_rooms = {}  # {user_id: set(room_ids)}
        self.logger = logging.getLogger(__name__)
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize SocketIO with Flask app"""
        self.socketio = SocketIO(
            app,
            cors_allowed_origins="*",
            async_mode='eventlet',
            logger=True,
            engineio_logger=True,
            ping_timeout=60,
            ping_interval=25
        )
        
        # Register event handlers
        self._register_handlers()
        
        # Start cleanup task
        self.socketio.start_background_task(self._cleanup_inactive_connections)
    
    def _register_handlers(self):
        """Register all WebSocket event handlers"""
        
        @self.socketio.on('connect')
        def handle_connect(auth):
            """Handle client connection"""
            try:
                # Verify authentication
                if not auth or 'token' not in auth:
                    self.logger.warning(f"Unauthenticated connection attempt from {request.remote_addr}")
                    disconnect()
                    return False
                
                # Verify session token
                from .auth import verify_token
                user = self._verify_session_token(auth['token'])
                if not user:
                    self.logger.warning(f"Invalid token connection attempt from {request.remote_addr}")
                    disconnect()
                    return False
                
                # Store connection info
                session_id = request.sid
                self.active_connections[session_id] = {
                    'user_id': user.id,
                    'username': user.username,
                    'rooms': set(),
                    'connected_at': datetime.utcnow(),
                    'ip_address': request.remote_addr
                }
                
                # Initialize user rooms if not exists
                if user.id not in self.user_rooms:
                    self.user_rooms[user.id] = set()
                
                # Log connection
                log_security_event('INFO', f'WebSocket connection: {user.username}', user.id, {
                    'session_id': session_id,
                    'ip_address': request.remote_addr
                })
                
                # Send connection success
                emit('connected', {
                    'user_id': user.id,
                    'username': user.username,
                    'session_id': session_id,
                    'timestamp': datetime.utcnow().isoformat()
                })
                
                # Send user's available rooms
                self._send_available_rooms(user.id)
                
                self.logger.info(f"User {user.username} connected via WebSocket")
                return True
                
            except Exception as e:
                self.logger.error(f"Connection error: {e}")
                disconnect()
                return False
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            """Handle client disconnection"""
            try:
                session_id = request.sid
                if session_id in self.active_connections:
                    conn_info = self.active_connections[session_id]
                    user_id = conn_info['user_id']
                    username = conn_info['username']
                    
                    # Leave all rooms
                    for room_id in conn_info['rooms'].copy():
                        self._leave_room_internal(session_id, room_id)
                    
                    # Remove connection
                    del self.active_connections[session_id]
                    
                    # Log disconnection
                    log_security_event('INFO', f'WebSocket disconnection: {username}', user_id, {
                        'session_id': session_id
                    })
                    
                    self.logger.info(f"User {username} disconnected from WebSocket")
                
            except Exception as e:
                self.logger.error(f"Disconnection error: {e}")
        
        @self.socketio.on('join_room')
        def handle_join_room(data):
            """Handle user joining a chat room"""
            try:
                session_id = request.sid
                if session_id not in self.active_connections:
                    emit('error', {'message': 'Not authenticated'})
                    return
                
                room_id = data.get('room_id')
                if not room_id:
                    emit('error', {'message': 'Room ID required'})
                    return
                
                user_id = self.active_connections[session_id]['user_id']
                
                # Verify room exists and user has access
                room = ChatRoom.query.get(room_id)
                if not room or not room.is_active:
                    emit('error', {'message': 'Room not found or inactive'})
                    return
                
                # Check if room is public or user has access
                if not room.is_public:
                    user_room = UserRoom.query.filter_by(
                        user_id=user_id,
                        room_id=room_id,
                        is_active=True
                    ).first()
                    if not user_room:
                        emit('error', {'message': 'Access denied to private room'})
                        return
                
                # Join the room
                join_room(room_id)
                self.active_connections[session_id]['rooms'].add(room_id)
                
                # Update room users tracking
                if room_id not in self.room_users:
                    self.room_users[room_id] = set()
                self.room_users[room_id].add(user_id)
                self.user_rooms[user_id].add(room_id)
                
                # Update user room record
                user_room = UserRoom.query.filter_by(
                    user_id=user_id,
                    room_id=room_id
                ).first()
                
                if not user_room:
                    user_room = UserRoom(
                        user_id=user_id,
                        room_id=room_id,
                        is_active=True
                    )
                    db.session.add(user_room)
                else:
                    user_room.is_active = True
                    user_room.left_at = None
                
                db.session.commit()
                
                # Notify room members
                username = self.active_connections[session_id]['username']
                self.socketio.emit('user_joined', {
                    'user_id': user_id,
                    'username': username,
                    'room_id': room_id,
                    'timestamp': datetime.utcnow().isoformat()
                }, room=room_id)
                
                # Send room info to user
                emit('room_joined', {
                    'room_id': room_id,
                    'room_name': room.name,
                    'user_count': len(self.room_users.get(room_id, set())),
                    'timestamp': datetime.utcnow().isoformat()
                })
                
                # Send recent messages
                self._send_recent_messages(room_id, user_id)
                
                self.logger.info(f"User {username} joined room {room.name}")
                
            except Exception as e:
                self.logger.error(f"Join room error: {e}")
                emit('error', {'message': 'Failed to join room'})
        
        @self.socketio.on('leave_room')
        def handle_leave_room(data):
            """Handle user leaving a chat room"""
            try:
                session_id = request.sid
                room_id = data.get('room_id')
                
                if session_id in self.active_connections and room_id:
                    self._leave_room_internal(session_id, room_id)
                    
            except Exception as e:
                self.logger.error(f"Leave room error: {e}")
                emit('error', {'message': 'Failed to leave room'})
        
        @self.socketio.on('send_message')
        def handle_send_message(data):
            """Handle sending a chat message"""
            try:
                session_id = request.sid
                if session_id not in self.active_connections:
                    emit('error', {'message': 'Not authenticated'})
                    return
                
                room_id = data.get('room_id')
                content = data.get('content', '').strip()
                message_type = data.get('type', 'text')
                
                if not room_id or not content:
                    emit('error', {'message': 'Room ID and content required'})
                    return
                
                user_id = self.active_connections[session_id]['user_id']
                username = self.active_connections[session_id]['username']
                
                # Verify user is in room
                if room_id not in self.active_connections[session_id]['rooms']:
                    emit('error', {'message': 'You are not in this room'})
                    return
                
                # Check user permissions
                user_room = UserRoom.query.filter_by(
                    user_id=user_id,
                    room_id=room_id,
                    is_active=True
                ).first()
                
                if user_room and not user_room.can_send_messages:
                    emit('error', {'message': 'You do not have permission to send messages'})
                    return
                
                # Create message record
                message = ChatMessage(
                    user_id=user_id,
                    room_id=room_id,
                    content=content,
                    message_type=message_type
                )
                db.session.add(message)
                db.session.commit()
                
                # Broadcast message to room
                message_data = {
                    'id': message.id,
                    'user_id': user_id,
                    'username': username,
                    'content': content,
                    'type': message_type,
                    'timestamp': message.created_at.isoformat(),
                    'room_id': room_id
                }
                
                self.socketio.emit('new_message', message_data, room=room_id)
                
                self.logger.info(f"Message sent by {username} in room {room_id}")
                
            except Exception as e:
                self.logger.error(f"Send message error: {e}")
                emit('error', {'message': 'Failed to send message'})
        
        @self.socketio.on('typing_start')
        def handle_typing_start(data):
            """Handle typing indicator start"""
            try:
                session_id = request.sid
                room_id = data.get('room_id')
                
                if session_id in self.active_connections and room_id:
                    if room_id in self.active_connections[session_id]['rooms']:
                        username = self.active_connections[session_id]['username']
                        self.socketio.emit('user_typing', {
                            'username': username,
                            'room_id': room_id,
                            'typing': True
                        }, room=room_id, include_self=False)
                        
            except Exception as e:
                self.logger.error(f"Typing start error: {e}")
        
        @self.socketio.on('typing_stop')
        def handle_typing_stop(data):
            """Handle typing indicator stop"""
            try:
                session_id = request.sid
                room_id = data.get('room_id')
                
                if session_id in self.active_connections and room_id:
                    if room_id in self.active_connections[session_id]['rooms']:
                        username = self.active_connections[session_id]['username']
                        self.socketio.emit('user_typing', {
                            'username': username,
                            'room_id': room_id,
                            'typing': False
                        }, room=room_id, include_self=False)
                        
            except Exception as e:
                self.logger.error(f"Typing stop error: {e}")
        
        @self.socketio.on('get_room_users')
        def handle_get_room_users(data):
            """Get list of users in a room"""
            try:
                session_id = request.sid
                room_id = data.get('room_id')
                
                if session_id not in self.active_connections:
                    emit('error', {'message': 'Not authenticated'})
                    return
                
                if room_id not in self.active_connections[session_id]['rooms']:
                    emit('error', {'message': 'You are not in this room'})
                    return
                
                # Get active users in room
                room_user_ids = self.room_users.get(room_id, set())
                users_data = []
                
                for user_id in room_user_ids:
                    user = User.query.get(user_id)
                    if user:
                        users_data.append({
                            'id': user.id,
                            'username': user.username,
                            'avatar_url': user.avatar_url,
                            'online': any(
                                conn['user_id'] == user_id 
                                for conn in self.active_connections.values()
                            )
                        })
                
                emit('room_users', {
                    'room_id': room_id,
                    'users': users_data
                })
                
            except Exception as e:
                self.logger.error(f"Get room users error: {e}")
                emit('error', {'message': 'Failed to get room users'})
    
    def _verify_session_token(self, token: str) -> Optional[User]:
        """Verify session token and return user"""
        try:
            from .models import UserSession
            
            user_session = UserSession.query.filter_by(
                session_token=token,
                is_active=True
            ).first()
            
            if not user_session or user_session.is_expired():
                return None
            
            user = User.query.get(user_session.user_id)
            if not user or not user.is_active_user():
                return None
            
            return user
            
        except Exception as e:
            self.logger.error(f"Token verification error: {e}")
            return None
    
    def _leave_room_internal(self, session_id: str, room_id: str):
        """Internal method to handle leaving a room"""
        try:
            if session_id not in self.active_connections:
                return
            
            conn_info = self.active_connections[session_id]
            user_id = conn_info['user_id']
            username = conn_info['username']
            
            # Leave the room
            leave_room(room_id)
            conn_info['rooms'].discard(room_id)
            
            # Update tracking
            if room_id in self.room_users:
                self.room_users[room_id].discard(user_id)
            if user_id in self.user_rooms:
                self.user_rooms[user_id].discard(room_id)
            
            # Update database
            user_room = UserRoom.query.filter_by(
                user_id=user_id,
                room_id=room_id
            ).first()
            
            if user_room:
                user_room.is_active = False
                user_room.left_at = datetime.utcnow()
                db.session.commit()
            
            # Notify room members
            self.socketio.emit('user_left', {
                'user_id': user_id,
                'username': username,
                'room_id': room_id,
                'timestamp': datetime.utcnow().isoformat()
            }, room=room_id)
            
            # Confirm to user
            self.socketio.emit('room_left', {
                'room_id': room_id,
                'timestamp': datetime.utcnow().isoformat()
            }, room=session_id)
            
            self.logger.info(f"User {username} left room {room_id}")
            
        except Exception as e:
            self.logger.error(f"Leave room internal error: {e}")
    
    def _send_available_rooms(self, user_id: str):
        """Send list of available rooms to user"""
        try:
            # Get public rooms and user's private rooms
            public_rooms = ChatRoom.query.filter_by(is_public=True, is_active=True).all()
            
            user_private_rooms = db.session.query(ChatRoom).join(UserRoom).filter(
                UserRoom.user_id == user_id,
                UserRoom.is_active == True,
                ChatRoom.is_public == False,
                ChatRoom.is_active == True
            ).all()
            
            rooms_data = []
            for room in public_rooms + user_private_rooms:
                rooms_data.append({
                    'id': room.id,
                    'name': room.name,
                    'description': room.description,
                    'is_public': room.is_public,
                    'user_count': len(self.room_users.get(room.id, set()))
                })
            
            # Find user's session
            user_session = None
            for session_id, conn_info in self.active_connections.items():
                if conn_info['user_id'] == user_id:
                    user_session = session_id
                    break
            
            if user_session:
                self.socketio.emit('available_rooms', {
                    'rooms': rooms_data
                }, room=user_session)
                
        except Exception as e:
            self.logger.error(f"Send available rooms error: {e}")
    
    def _send_recent_messages(self, room_id: str, user_id: str, limit: int = 50):
        """Send recent messages from a room to user"""
        try:
            messages = ChatMessage.query.filter_by(
                room_id=room_id,
                is_deleted=False
            ).order_by(ChatMessage.created_at.desc()).limit(limit).all()
            
            messages_data = []
            for message in reversed(messages):  # Reverse to get chronological order
                messages_data.append(message.to_dict())
            
            # Find user's session
            user_session = None
            for session_id, conn_info in self.active_connections.items():
                if conn_info['user_id'] == user_id:
                    user_session = session_id
                    break
            
            if user_session:
                self.socketio.emit('recent_messages', {
                    'room_id': room_id,
                    'messages': messages_data
                }, room=user_session)
                
        except Exception as e:
            self.logger.error(f"Send recent messages error: {e}")
    
    def _cleanup_inactive_connections(self):
        """Background task to cleanup inactive connections"""
        while True:
            try:
                current_time = datetime.utcnow()
                inactive_sessions = []
                
                for session_id, conn_info in self.active_connections.items():
                    # Check if connection is older than 24 hours
                    if (current_time - conn_info['connected_at']).total_seconds() > 86400:
                        inactive_sessions.append(session_id)
                
                # Clean up inactive sessions
                for session_id in inactive_sessions:
                    if session_id in self.active_connections:
                        conn_info = self.active_connections[session_id]
                        # Leave all rooms
                        for room_id in conn_info['rooms'].copy():
                            self._leave_room_internal(session_id, room_id)
                        # Remove connection
                        del self.active_connections[session_id]
                        self.logger.info(f"Cleaned up inactive connection: {session_id}")
                
                # Sleep for 1 hour before next cleanup
                self.socketio.sleep(3600)
                
            except Exception as e:
                self.logger.error(f"Cleanup task error: {e}")
                self.socketio.sleep(3600)
    
    def broadcast_system_message(self, room_id: str, message: str, message_type: str = 'system'):
        """Broadcast a system message to a room"""
        try:
            if room_id in self.room_users:
                self.socketio.emit('system_message', {
                    'content': message,
                    'type': message_type,
                    'timestamp': datetime.utcnow().isoformat(),
                    'room_id': room_id
                }, room=room_id)
                
        except Exception as e:
            self.logger.error(f"Broadcast system message error: {e}")
    
    def send_notification(self, user_id: str, notification: Dict):
        """Send a notification to a specific user"""
        try:
            # Find user's active sessions
            for session_id, conn_info in self.active_connections.items():
                if conn_info['user_id'] == user_id:
                    self.socketio.emit('notification', notification, room=session_id)
                    
        except Exception as e:
            self.logger.error(f"Send notification error: {e}")
    
    def get_active_users(self) -> List[Dict]:
        """Get list of currently active users"""
        try:
            active_users = {}
            for conn_info in self.active_connections.values():
                user_id = conn_info['user_id']
                if user_id not in active_users:
                    active_users[user_id] = {
                        'user_id': user_id,
                        'username': conn_info['username'],
                        'connected_at': conn_info['connected_at'].isoformat(),
                        'rooms': len(conn_info['rooms']),
                        'connections': 1
                    }
                else:
                    active_users[user_id]['connections'] += 1
            
            return list(active_users.values())
            
        except Exception as e:
            self.logger.error(f"Get active users error: {e}")
            return []
    
    def get_room_stats(self) -> Dict:
        """Get statistics about active rooms"""
        try:
            stats = {
                'total_rooms': len(self.room_users),
                'active_connections': len(self.active_connections),
                'rooms': {}
            }
            
            for room_id, user_ids in self.room_users.items():
                room = ChatRoom.query.get(room_id)
                if room:
                    stats['rooms'][room_id] = {
                        'name': room.name,
                        'user_count': len(user_ids),
                        'is_public': room.is_public
                    }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Get room stats error: {e}")
            return {'error': str(e)}

# Global WebSocket manager instance
websocket_manager = WebSocketManager()