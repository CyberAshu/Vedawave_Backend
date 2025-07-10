from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import json
import asyncio
from datetime import datetime, timedelta
import uuid
import os

from database import get_db, init_db
from models import User, Chat, Message, Attachment, FriendRequest, Friendship, MessageReaction
from schemas import UserCreate, UserLogin, ChatCreate, MessageCreate, UserResponse, ChatResponse, MessageResponse, FriendRequestCreate, FriendRequestResponse, FriendRequestUpdate, FriendshipResponse, UserUpdate
from auth import create_access_token, verify_token, get_password_hash, verify_password
from websocket_manager import ConnectionManager
from sqlalchemy import or_, and_

app = FastAPI(title="Vedawave API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for uploads
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# WebSocket connection manager
manager = ConnectionManager()

# Security
security = HTTPBearer()

# Initialize database
@app.on_event("startup")
async def startup_event():
    await init_db()

# Auth dependency
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    return user

# Auth routes
@app.post("/api/auth/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    # Check if user exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    user = User(
        name=user_data.name,
        email=user_data.email,
        password=hashed_password,
        avatar=user_data.avatar
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user.id)})
    
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        avatar=user.avatar,
        is_active=user.is_active,
        access_token=access_token
    )

@app.post("/api/auth/login", response_model=UserResponse)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_data.email).first()
    if not user or not verify_password(user_data.password, user.password):
        raise HTTPException(status_code=400, detail="Invalid email or password")
    
    # Update user status
    user.is_active = True
    user.last_seen = datetime.utcnow()
    db.commit()
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user.id)})
    
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        avatar=user.avatar,
        is_active=user.is_active,
        access_token=access_token
    )

@app.post("/api/auth/logout")
async def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.is_active = False
    current_user.last_seen = datetime.utcnow()
    db.commit()
    return {"message": "Logged out successfully"}

# User routes
@app.get("/api/users", response_model=List[UserResponse])
async def get_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.id != current_user.id).all()
    return [UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        avatar=user.avatar,
        is_active=user.is_active
    ) for user in users]

@app.get("/api/users/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        avatar=current_user.avatar,
        is_active=current_user.is_active
    )

@app.put("/api/users/me", response_model=UserResponse)
async def update_current_user(user_data: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Update user fields
    if user_data.name:
        current_user.name = user_data.name
    if user_data.email:
        # Check if email is already taken by another user
        existing_user = db.query(User).filter(User.email == user_data.email, User.id != current_user.id).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        current_user.email = user_data.email
    if user_data.avatar:
        current_user.avatar = user_data.avatar
    
    db.commit()
    db.refresh(current_user)
    
    return UserResponse(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        avatar=current_user.avatar,
        is_active=current_user.is_active
    )

@app.get("/api/users/search", response_model=List[UserResponse])
async def search_users(q: str = "", current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Get current user's friends
    friendships = db.query(Friendship).filter(
        or_(Friendship.user1_id == current_user.id, Friendship.user2_id == current_user.id)
    ).all()
    friend_ids = set()
    for friendship in friendships:
        friend_id = friendship.user2_id if friendship.user1_id == current_user.id else friendship.user1_id
        friend_ids.add(friend_id)
    
    # Get pending friend requests (both sent and received)
    pending_requests = db.query(FriendRequest).filter(
        or_(FriendRequest.sender_id == current_user.id, FriendRequest.receiver_id == current_user.id),
        FriendRequest.status == "pending"
    ).all()
    pending_ids = set()
    for req in pending_requests:
        other_id = req.receiver_id if req.sender_id == current_user.id else req.sender_id
        pending_ids.add(other_id)
    
    # Exclude current user, friends, and users with pending requests
    exclude_ids = friend_ids.union(pending_ids)
    exclude_ids.add(current_user.id)
    
    query = db.query(User).filter(User.id.notin_(exclude_ids))
    
    if q:
        query = query.filter(
            or_(User.name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"))
        )
    
    users = query.limit(20).all()
    return [UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        avatar=user.avatar,
        is_active=user.is_active
    ) for user in users]

# Chat routes
@app.get("/api/chats", response_model=List[ChatResponse])
async def get_chats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chats = db.query(Chat).filter(
        (Chat.user1_id == current_user.id) | (Chat.user2_id == current_user.id)
    ).all()
    
    chat_responses = []
    for chat in chats:
        other_user_id = chat.user2_id if chat.user1_id == current_user.id else chat.user1_id
        other_user = db.query(User).filter(User.id == other_user_id).first()
        
        last_message = db.query(Message).filter(Message.chat_id == chat.id).order_by(Message.created_at.desc()).first()
        
        # Calculate unread message count
        unread_count = db.query(Message).filter(
            Message.chat_id == chat.id,
            Message.sender_id != current_user.id,
            Message.status != 'seen'
        ).count()

        chat_responses.append(ChatResponse(
            id=chat.id,
            other_user=UserResponse(
                id=other_user.id,
                name=other_user.name,
                email=other_user.email,
                avatar=other_user.avatar,
                is_active=other_user.is_active
            ),
            last_message=MessageResponse(
                id=last_message.id,
                content=last_message.content,
                sender_id=last_message.sender_id,
                created_at=last_message.created_at,
                message_type=last_message.message_type,
                is_edited=last_message.is_edited,
                is_deleted=last_message.is_deleted,
                attachments=[]
            ) if last_message else None,
            created_at=chat.created_at,
            unread_count=unread_count
        ))
    
    return sorted(chat_responses, key=lambda x: x.last_message.created_at if x.last_message else x.created_at, reverse=True)

@app.post("/api/chats", response_model=ChatResponse)
async def create_chat(chat_data: ChatCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Check if chat already exists
    existing_chat = db.query(Chat).filter(
        ((Chat.user1_id == current_user.id) & (Chat.user2_id == chat_data.user_id)) |
        ((Chat.user1_id == chat_data.user_id) & (Chat.user2_id == current_user.id))
    ).first()
    
    if existing_chat:
        other_user = db.query(User).filter(User.id == chat_data.user_id).first()
        return ChatResponse(
            id=existing_chat.id,
            other_user=UserResponse(
                id=other_user.id,
                name=other_user.name,
                email=other_user.email,
                avatar=other_user.avatar,
                is_active=other_user.is_active
            ),
            last_message=None,
            created_at=existing_chat.created_at
        )
    
    # Create new chat
    chat = Chat(user1_id=current_user.id, user2_id=chat_data.user_id)
    db.add(chat)
    db.commit()
    db.refresh(chat)
    
    other_user = db.query(User).filter(User.id == chat_data.user_id).first()
    
    return ChatResponse(
        id=chat.id,
        other_user=UserResponse(
            id=other_user.id,
            name=other_user.name,
            email=other_user.email,
            avatar=other_user.avatar,
            is_active=other_user.is_active
        ),
        last_message=None,
        created_at=chat.created_at
    )

# Friend request routes
@app.post("/api/friend-requests", response_model=FriendRequestResponse)
async def create_friend_request(
    friend_request: FriendRequestCreate, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)):
    
    # Check if a request already exists
    existing_request = db.query(FriendRequest).filter(
        or_(and_(FriendRequest.sender_id == current_user.id, FriendRequest.receiver_id == friend_request.receiver_id),
             and_(FriendRequest.sender_id == friend_request.receiver_id, FriendRequest.receiver_id == current_user.id))
    ).first()
    
    if existing_request:
        raise HTTPException(status_code=400, detail="Friend request already exists")

    # Create new friend request
    new_request = FriendRequest(
        sender_id=current_user.id,
        receiver_id=friend_request.receiver_id
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)
    
    # Send real-time notification to receiver
    notification_data = {
        "type": "friend_request",
        "action": "received",
        "request": {
            "id": new_request.id,
            "sender": {
                "id": current_user.id,
                "name": current_user.name,
                "email": current_user.email,
                "avatar": current_user.avatar
            },
            "status": new_request.status,
            "created_at": new_request.created_at.isoformat()
        }
    }
    await manager.send_to_user(friend_request.receiver_id, json.dumps(notification_data))
    
    return FriendRequestResponse(
        id=new_request.id,
        sender=UserResponse(
            id=new_request.sender.id,
            name=new_request.sender.name,
            email=new_request.sender.email,
            avatar=new_request.sender.avatar,
            is_active=new_request.sender.is_active
        ),
        receiver=UserResponse(
            id=new_request.receiver.id,
            name=new_request.receiver.name,
            email=new_request.receiver.email,
            avatar=new_request.receiver.avatar,
            is_active=new_request.receiver.is_active
        ),
        status=new_request.status,
        created_at=new_request.created_at
    )

@app.get("/api/friend-requests", response_model=List[FriendRequestResponse])
async def get_friend_requests(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    requests = db.query(FriendRequest).filter(
        or_(FriendRequest.sender_id == current_user.id, FriendRequest.receiver_id == current_user.id)
    ).all()
    return [FriendRequestResponse(
        id=req.id,
        sender=UserResponse(
            id=req.sender.id,
            name=req.sender.name,
            email=req.sender.email,
            avatar=req.sender.avatar,
            is_active=req.sender.is_active
        ),
        receiver=UserResponse(
            id=req.receiver.id,
            name=req.receiver.name,
            email=req.receiver.email,
            avatar=req.receiver.avatar,
            is_active=req.receiver.is_active
        ),
        status=req.status,
        created_at=req.created_at
    ) for req in requests]

@app.put("/api/friend-requests/{request_id}", response_model=FriendRequestResponse)
async def update_friend_request(request_id: int, request_update: FriendRequestUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    request = db.query(FriendRequest).filter(
        FriendRequest.id == request_id,
        FriendRequest.receiver_id == current_user.id
    ).first()
    
    if not request:
        raise HTTPException(status_code=404, detail="Friend request not found")

    request.status = request_update.status
    db.commit()
    db.refresh(request)

    if request.status == "accepted":
        # Create a friendship
        friendship = Friendship(user1_id=request.sender_id, user2_id=request.receiver_id)
        db.add(friendship)
        db.commit()

    return FriendRequestResponse(
        id=request.id,
        sender=UserResponse(
            id=request.sender.id,
            name=request.sender.name,
            email=request.sender.email,
            avatar=request.sender.avatar,
            is_active=request.sender.is_active
        ),
        receiver=UserResponse(
            id=request.receiver.id,
            name=request.receiver.name,
            email=request.receiver.email,
            avatar=request.receiver.avatar,
            is_active=request.receiver.is_active
        ),
        status=request.status,
        created_at=request.created_at
    )

@app.get("/api/friends", response_model=List[FriendshipResponse])
async def get_friends(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    friendships = db.query(Friendship).filter(
        or_(Friendship.user1_id == current_user.id, Friendship.user2_id == current_user.id)
    ).all()
    
    friends = []
    for friendship in friendships:
        friend_id = friendship.user2_id if friendship.user1_id == current_user.id else friendship.user1_id
        friend = db.query(User).filter(User.id == friend_id).first()
        friends.append(FriendshipResponse(
            id=friendship.id,
            friend=UserResponse(
                id=friend.id,
                name=friend.name,
                email=friend.email,
                avatar=friend.avatar,
                is_active=friend.is_active
            ),
            created_at=friendship.created_at
        ))
    return friends

# Message routes
@app.get("/api/chats/{chat_id}/messages", response_model=List[MessageResponse])
async def get_messages(chat_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Verify user is part of the chat
    chat = db.query(Chat).filter(
        Chat.id == chat_id,
        ((Chat.user1_id == current_user.id) | (Chat.user2_id == current_user.id))
    ).first()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    messages = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.created_at.asc()).all()
    
    # Mark messages as seen for the current user and notify senders
    seen_messages = []
    for message in messages:
        if message.sender_id != current_user.id and message.status != 'seen':
            message.status = 'seen'
            message.seen_at = datetime.utcnow()
            seen_messages.append(message)
    
    if seen_messages:
        db.commit()
        
        # Notify message senders that their messages have been seen
        for message in seen_messages:
            await manager.update_message_status(message.id, 'seen', message.chat_id, message.sender_id)
    
    message_responses = []
    for message in messages:
        attachments = db.query(Attachment).filter(Attachment.message_id == message.id).all()
        
        # Get reply to message info if exists
        reply_to_message = None
        if message.reply_to_message_id:
            reply_msg = db.query(Message).filter(Message.id == message.reply_to_message_id).first()
            if reply_msg:
                reply_to_message = {
                    "id": reply_msg.id,
                    "content": reply_msg.content,
                    "sender_id": reply_msg.sender_id,
                    "created_at": reply_msg.created_at.isoformat(),
                    "message_type": reply_msg.message_type,
                    "is_deleted": reply_msg.is_deleted
                }
        
        # Get reactions for this message
        reactions = db.query(MessageReaction).filter(MessageReaction.message_id == message.id).all()
        
        # Group reactions by emoji
        reaction_groups = {}
        for r in reactions:
            if r.emoji not in reaction_groups:
                reaction_groups[r.emoji] = []
            reaction_groups[r.emoji].append(r.user_id)
        
        # Format reactions
        formatted_reactions = []
        for emoji, user_ids in reaction_groups.items():
            formatted_reactions.append({
                "emoji": emoji,
                "count": len(user_ids),
                "users": user_ids
            })
        
        # Format attachments
        formatted_attachments = [{
            "id": att.id,
            "filename": att.filename,
            "file_url": att.file_url,
            "file_type": att.file_type,
            "file_size": att.file_size
        } for att in attachments]
        
        message_responses.append(MessageResponse(
            id=message.id,
            content=message.content,
            sender_id=message.sender_id,
            created_at=message.created_at,
            message_type=message.message_type,
            is_edited=message.is_edited,
            is_deleted=message.is_deleted,
            status=message.status,
            reply_to_message_id=message.reply_to_message_id,
            reply_to_message=reply_to_message,
            attachments=formatted_attachments,
            reactions=formatted_reactions
        ))
    
    return message_responses

@app.put("/api/messages/{message_id}", response_model=MessageResponse)
async def edit_message(message_id: int, message_data: MessageCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Get the message
    message = db.query(Message).filter(Message.id == message_id).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Check if user is the sender
    if message.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own messages")
    
    # Update message content
    message.content = message_data.content
    message.is_edited = True
    db.commit()
    db.refresh(message)
    
    # Broadcast message edit to chat participants
    chat = db.query(Chat).filter(Chat.id == message.chat_id).first()
    participants = [chat.user1_id, chat.user2_id]
    
    edit_data = {
        "type": "message_edited",
        "message_id": message_id,
        "chat_id": message.chat_id,
        "content": message.content,
        "is_edited": True,
        "edited_by": current_user.id
    }
    await manager.send_to_users(participants, json.dumps(edit_data))
    
    return MessageResponse(
        id=message.id,
        content=message.content,
        sender_id=message.sender_id,
        created_at=message.created_at,
        message_type=message.message_type,
        is_edited=True,
        is_deleted=message.is_deleted,
        attachments=[]
    )

class ReactionRequest(BaseModel):
    emoji: str

@app.post("/api/messages/{message_id}/reactions")
async def add_reaction(
    message_id: int,
    reaction_data: ReactionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Check for existing reaction
    existing_reaction = db.query(MessageReaction).filter_by(
        message_id=message_id,
        user_id=current_user.id,
        emoji=reaction_data.emoji
    ).first()
    
    action = "removed"
    if existing_reaction:
        # Remove existing reaction
        db.delete(existing_reaction)
        db.commit()
        action = "removed"
    else:
        # Add new reaction
        new_reaction = MessageReaction(
            message_id=message_id,
            user_id=current_user.id,
            emoji=reaction_data.emoji
        )
        db.add(new_reaction)
        db.commit()
        action = "added"
    
    # Get chat info for broadcasting
    chat = db.query(Chat).filter(Chat.id == message.chat_id).first()
    participants = [chat.user1_id, chat.user2_id]
    
    # Get all reactions for this message after the add/remove operation
    reactions = db.query(MessageReaction).filter(MessageReaction.message_id == message_id).all()
    
    # Group reactions by emoji
    reaction_groups = {}
    for r in reactions:
        if r.emoji not in reaction_groups:
            reaction_groups[r.emoji] = []
        reaction_groups[r.emoji].append(r.user_id)
    
    # Format reactions for broadcast
    formatted_reactions = []
    for emoji, user_ids in reaction_groups.items():
        formatted_reactions.append({
            "emoji": emoji,
            "count": len(user_ids),
            "users": user_ids
        })
    
    # Broadcast updated reactions to chat participants
    broadcast_data = {
        "type": "reaction",
        "action": action,
        "message_id": message_id,
        "chat_id": message.chat_id,
        "user_id": current_user.id,
        "emoji": reaction_data.emoji,
        "reactions": formatted_reactions
    }
    await manager.send_to_users(participants, json.dumps(broadcast_data))
    
    return {"message": f"Reaction {action} successfully", "action": action, "reactions": formatted_reactions}

@app.delete("/api/messages/{message_id}")
async def delete_message(message_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Get the message
    message = db.query(Message).filter(Message.id == message_id).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Check if user is the sender
    if message.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own messages")
    
    # Get chat info for broadcasting
    chat = db.query(Chat).filter(Chat.id == message.chat_id).first()
    participants = [chat.user1_id, chat.user2_id]
    
    # Mark as deleted instead of actually deleting
    message.is_deleted = True
    message.content = "This message was deleted"
    db.commit()
    
    # Broadcast deletion to chat participants
    deletion_data = {
        "type": "message_deleted",
        "message_id": message_id,
        "chat_id": message.chat_id,
        "deleted_by": current_user.id
    }
    await manager.send_to_users(participants, json.dumps(deletion_data))
    
    return {"message": "Message deleted successfully"}

# File upload
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    file_id = str(uuid.uuid4())
    file_extension = os.path.splitext(file.filename)[1]
    filename = f"{file_id}{file_extension}"
    file_path = f"uploads/{filename}"
    
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    return {
        "filename": file.filename,
        "file_url": f"/uploads/{filename}",
        "file_type": file.content_type,
        "file_size": len(content)
    }

# WebSocket endpoint
@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str, db: Session = Depends(get_db)):
    # Verify token
    user_id = verify_token(token)
    if not user_id:
        await websocket.close(code=4001)
        return
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        await websocket.close(code=4001)
        return
    
    await manager.connect(websocket, user_id)
    
    # Update user status
    user.is_active = True
    user.last_seen = datetime.utcnow()
    db.commit()
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data["type"] == "message":
                # Save message to database
                message = Message(
                    content=message_data["content"],
                    sender_id=user_id,
                    chat_id=message_data["chat_id"],
                    message_type=message_data.get("message_type", "text"),
                    reply_to_message_id=message_data.get("reply_to_message_id")
                )
                db.add(message)
                db.commit()
                db.refresh(message)
                
                # Save attachments if any
                attachments = []
                if message_data.get("attachments"):
                    for att_data in message_data["attachments"]:
                        attachment = Attachment(
                            message_id=message.id,
                            filename=att_data["filename"],
                            file_url=att_data["file_url"],
                            file_type=att_data["file_type"],
                            file_size=att_data["file_size"]
                        )
                        db.add(attachment)
                        attachments.append({
                            "filename": attachment.filename,
                            "file_url": attachment.file_url,
                            "file_type": attachment.file_type,
                            "file_size": attachment.file_size
                        })
                    db.commit()
                
                # Get chat participants
                chat = db.query(Chat).filter(Chat.id == message_data["chat_id"]).first()
                participants = [chat.user1_id, chat.user2_id]
                
                # Get reply to message info if exists
                reply_to_message = None
                if message.reply_to_message_id:
                    reply_msg = db.query(Message).filter(Message.id == message.reply_to_message_id).first()
                    if reply_msg:
                        reply_to_message = {
                            "id": reply_msg.id,
                            "content": reply_msg.content,
                            "sender_id": reply_msg.sender_id,
                            "created_at": reply_msg.created_at.isoformat(),
                            "message_type": reply_msg.message_type,
                            "is_deleted": reply_msg.is_deleted
                        }
                
                # Send message to chat participants
                response_data = {
                    "type": "message",
                    "message": {
                        "id": message.id,
                        "content": message.content,
                        "sender_id": message.sender_id,
                        "chat_id": message.chat_id,
                        "created_at": message.created_at.isoformat(),
                        "message_type": message.message_type,
                        "reply_to_message_id": message.reply_to_message_id,
                        "reply_to_message": reply_to_message,
                        "attachments": attachments
                    }
                }
                
                await manager.send_to_users(participants, json.dumps(response_data))
                
                # Send delivery status
                for participant_id in participants:
                    if participant_id != user_id:
                        await manager.update_message_status(message.id, "delivered", message.chat_id, participant_id)
                        message.delivered_at = datetime.utcnow()
                db.commit()
                
            elif message_data["type"] == "typing":
                # Handle typing indicator
                chat = db.query(Chat).filter(Chat.id == message_data["chat_id"]).first()
                other_user_id = chat.user2_id if chat.user1_id == user_id else chat.user1_id
                
                typing_data = {
                    "type": "typing",
                    "user_id": user_id,
                    "chat_id": message_data["chat_id"],
                    "is_typing": message_data["is_typing"]
                }
                
                await manager.send_to_user(other_user_id, json.dumps(typing_data))
                
            elif message_data["type"] == "ping":
                # Handle ping for heartbeat
                pong_data = {"type": "pong"}
                await websocket.send_text(json.dumps(pong_data))
    
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        # Update user status
        user.is_active = False
        user.last_seen = datetime.utcnow()
        db.commit()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
