from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any, ForwardRef
from datetime import datetime

# User schemas
class UserBase(BaseModel):
    name: str
    email: EmailStr

class UserCreate(UserBase):
    password: str
    avatar: Optional[str] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    avatar: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserBase):
    id: int
    avatar: Optional[str] = None
    is_active: bool
    last_seen: Optional[datetime] = None
    access_token: Optional[str] = None
    
    class Config:
        from_attributes = True

# Reaction schemas (moved before Message schemas to resolve forward reference)
class MessageReactionSummary(BaseModel):
    emoji: str
    count: int
    users: List[int]

# Message schemas (moved before Chat schemas to resolve forward reference)
class MessageCreate(BaseModel):
    content: Optional[str] = None
    chat_id: int
    message_type: str = "text"
    reply_to_message_id: Optional[int] = None
    attachments: Optional[List[Dict[str, Any]]] = []

class AttachmentResponse(BaseModel):
    id: int
    filename: str
    file_url: str
    file_type: str
    file_size: int
    
    class Config:
        from_attributes = True

class MessageResponse(BaseModel):
    id: int
    content: str
    sender_id: int
    created_at: datetime
    message_type: str
    is_edited: bool = False
    is_deleted: bool = False
    status: str = "sent"
    reply_to_message_id: Optional[int] = None
    reply_to_message: Optional[Dict[str, Any]] = None
    attachments: List[Dict[str, Any]] = []
    reactions: List[MessageReactionSummary] = []
    
    class Config:
        from_attributes = True

# Chat schemas
class ChatCreate(BaseModel):
    user_id: int

class ChatResponse(BaseModel):
    id: int
    other_user: UserResponse
    last_message: Optional[MessageResponse] = None
    created_at: datetime
    unread_count: int
    
    class Config:
        from_attributes = True

# WebSocket message schemas
class WSMessage(BaseModel):
    type: str
    content: Optional[str] = None
    chat_id: Optional[int] = None
    message_type: Optional[str] = "text"
    reply_to_message_id: Optional[int] = None
    attachments: Optional[List[Dict[str, Any]]] = []

class WSTyping(BaseModel):
    type: str = "typing"
    chat_id: int
    is_typing: bool

# Friend request schemas
class FriendRequestCreate(BaseModel):
    receiver_id: int

class FriendRequestResponse(BaseModel):
    id: int
    sender: UserResponse
    receiver: UserResponse
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class FriendRequestUpdate(BaseModel):
    status: str  # accepted or rejected

class FriendshipResponse(BaseModel):
    id: int
    friend: UserResponse
    created_at: datetime
    
    class Config:
        from_attributes = True

# File upload schema
class FileUploadResponse(BaseModel):
    filename: str
    file_url: str
    file_type: str
    file_size: int

# Reaction schemas
class ReactionCreate(BaseModel):
    emoji: str

class ReactionResponse(BaseModel):
    id: int
    emoji: str
    user_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

