import pymongo
from passlib.context import CryptContext

# --- Configuration --- #
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "mcp_backend" # Correction du nom de la base de données pour correspondre à la configuration réelle

# --- Identifiants de l'administrateur à mettre à jour --- #
ADMIN_NAME = "diaoissa0290@gmail.com"
ADMIN_EMAIL = "diaoissa0290@gmail.com"
ADMIN_PASSWORD = "admin" # Le nouveau mot de passe sera 'admin'
ADMIN_ROLE = "admin"
ADMIN_STATUS = "active"

# Contexte pour le hachage du mot de passe (doit correspondre à votre projet)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def create_admin_user():
    """
    Se connecte à MongoDB, vérifie si l'admin existe déjà,
    et le crée ou le met à jour si nécessaire.
    """
    try:
        client = pymongo.MongoClient(MONGO_URI)
        db = client[DB_NAME]
        users_collection = db["users"]

        # Vérifier si l'utilisateur existe déjà
        admin_user = users_collection.find_one({"email": ADMIN_EMAIL})

        hashed_password = get_password_hash(ADMIN_PASSWORD)

        if admin_user:
            print(f"L'utilisateur '{ADMIN_EMAIL}' existe déjà. Mise à jour du mot de passe et du statut.")
            users_collection.update_one(
                {"email": ADMIN_EMAIL},
                {"$set": {"password": hashed_password, "status": ADMIN_STATUS, "role": ADMIN_ROLE}}
            )
            print("Utilisateur mis à jour avec succès.")
        else:
            print(f"Création de l'utilisateur admin '{ADMIN_EMAIL}'.")
            users_collection.insert_one({
                "name": ADMIN_NAME,
                "email": ADMIN_EMAIL,
                "password": hashed_password,
                "role": ADMIN_ROLE,
                "status": ADMIN_STATUS
            })
            print("Utilisateur admin créé avec succès.")

    except pymongo.errors.ConnectionFailure as e:
        print(f"Erreur de connexion à MongoDB : {e}")
    except Exception as e:
        print(f"Une erreur est survenue : {e}")
    finally:
        if 'client' in locals() and client:
            client.close()

if __name__ == "__main__":
    create_admin_user()
