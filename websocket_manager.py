from fastapi import WebSocket
from typing import Dict, List
import json
import asyncio

class ConnectionManager:
    def __init__(self):
        # Store active connections: user_id -> websocket
        self.active_connections: Dict[int, WebSocket] = {}
        
    async def connect(self, websocket: WebSocket, user_id: int):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections[user_id] = websocket
        print(f"User {user_id} connected. Active connections: {len(self.active_connections)}")
        
    def disconnect(self, user_id: int):
        """Remove a WebSocket connection."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            print(f"User {user_id} disconnected. Active connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send a message to a specific WebSocket connection."""
        try:
            await websocket.send_text(message)
        except Exception as e:
            print(f"Error sending message: {e}")
    
    async def send_to_user(self, user_id: int, message: str):
        """Send a message to a specific user by user_id."""
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_text(message)
            except Exception as e:
                print(f"Error sending message to user {user_id}: {e}")
                # Remove disconnected connection
                self.disconnect(user_id)
    
    async def send_to_users(self, user_ids: List[int], message: str):
        """Send a message to multiple users."""
        tasks = []
        for user_id in user_ids:
            if user_id in self.active_connections:
                tasks.append(self.send_to_user(user_id, message))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def broadcast(self, message: str):
        """Broadcast a message to all connected users."""
        if not self.active_connections:
            return
        
        tasks = []
        for user_id, websocket in self.active_connections.items():
            tasks.append(self.send_personal_message(message, websocket))
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_active_users(self) -> List[int]:
        """Get list of currently active user IDs."""
        return list(self.active_connections.keys())
    
    def is_user_online(self, user_id: int) -> bool:
        """Check if a user is currently online."""
        return user_id in self.active_connections
    
    async def send_typing_indicator(self, chat_id: int, user_id: int, is_typing: bool, recipient_id: int):
        """Send typing indicator to the other user in a chat."""
        typing_data = {
            "type": "typing",
            "chat_id": chat_id,
            "user_id": user_id,
            "is_typing": is_typing
        }
        
        await self.send_to_user(recipient_id, json.dumps(typing_data))
    
    async def send_user_status_update(self, user_id: int, is_online: bool):
        """Send user status update to all connected users."""
        status_data = {
            "type": "user_status",
            "user_id": user_id,
            "is_online": is_online
        }
        
        await self.broadcast(json.dumps(status_data))
