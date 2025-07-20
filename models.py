from sqlalchemy import Column, Integer, String, Enum as SQLAlchemyEnum, DateTime, Text, JSON, func
from database import Base
import enum

# Définition des énumérations pour les rôles et statuts
# Cela garantit que seules les valeurs prédéfinies peuvent être utilisées.
class UserRole(str, enum.Enum):
    admin = "admin"
    agent_support = "agent_support"
    agent_interne = "agent_interne"
    client = "client"

class UserStatus(str, enum.Enum):
    active = "active"
    pending = "pending"
    rejected = "rejected"
    blocked = "blocked"

# Définition du modèle de données pour la table 'users'
# SQLAlchemy utilisera ce modèle pour interagir avec la table correspondante.
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SQLAlchemyEnum(UserRole), default=UserRole.client, nullable=False)
    status = Column(SQLAlchemyEnum(UserStatus), default=UserStatus.pending, nullable=False)
    glpi_user_id = Column(Integer, nullable=True)  # ID de l'utilisateur dans GLPI


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    content = Column(Text)
    category = Column(String, index=True)
    date_creation = Column(DateTime(timezone=True), server_default=func.now())
    roles_allowed = Column(JSON, nullable=False) # Stocke une liste de rôles, ex: ["admin", "voter"]
