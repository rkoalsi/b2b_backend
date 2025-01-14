from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import HTMLResponse
from backend.config.root import connect_to_mongo, disconnect_on_exit, parse_data  # type: ignore
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.hash import bcrypt

router = APIRouter()

client, db = connect_to_mongo()

# Password hashing setup

SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

client, db = connect_to_mongo()
users_collection = db["users"]


def verify_password(plain_password, hashed_password):
    return bcrypt.verify(plain_password, hashed_password)


def hash_password(password):
    return bcrypt.hash(password)


def find_user_by_email(email: str):
    user = db.users.find_one({"email": email})
    return True if user else False


def authenticate_user(email: str, password: str):
    user = db.users.find_one({"email": email})
    if not user or not verify_password(password, user["password"]):
        return False
    return parse_data(user)


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# Pydantic models
class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


@router.post("/register")
async def register_user(user: UserCreate):
    # Check if user already exists
    existing_user = find_user_by_email(user.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash the password
    hashed_password = hash_password(user.password)

    # Insert user into the database
    user_data = {"email": user.email, "password": hashed_password}
    result = users_collection.insert_one(user_data)
    if not result:
        raise HTTPException(status_code=400, detail="Error inserting user in database")

    access_token = create_access_token(data={"data": user["email"]})
    return {
        "message": "User registered successfully",
        "user_id": str(result.inserted_id),
        "access_token": access_token,
    }


@router.post("/login")
async def login_user(user: UserLogin):
    # Find user by email
    user = authenticate_user(user.email, user.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"data": user})
    return {
        "message": "Login successful",
        "user_id": user["_id"]["$oid"],
        "access_token": access_token,
    }


@router.get("/me")
async def read_users_me(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("data")
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication",
            )
        return {"email": email}
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


@router.get("/", response_class=HTMLResponse)
def index():
    return "<h1>Backend is running<h1>"
