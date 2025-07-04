from pymongo import MongoClient

# Connexion à MongoDB (localhost par défaut)
client = MongoClient("mongodb://localhost:27017/")
#permet  accès à une base de données spécifique 
def get_database(db_name="mcp_backend"):
    """
    Retourne la base de données MongoDB (par défaut : mcp_backend)
    """
    return client[db_name]
