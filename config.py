# config.py
"""
Fichier de configuration centralisée pour le backend MCP.
Tu pourras y mettre toutes les variables importantes (URLs, clés API, etc.)
"""

# Exemple de configuration (à adapter au fur et à mesure)
GLPI_API_URL = "http://localhost:8080/apirest.php/"
GLPI_APP_TOKEN = "PL7m6QX5VmD1KwZUJcVoAyGQBEtDas4B22UDAbAX"
GLPI_USER_TOKEN = "LFJ90GhinwkVphPt3H6001i5NBd5xnaNhfMAODlF"

# Configuration de la sécurité JWT (JSON Web Token)
SECRET_KEY = "a_very_secret_and_long_random_string_for_jwt_9876543210"  # IMPORTANT: Remplacez ceci par une vraie clé secrète en production
ALGORITHM = "HS256"

# Ajoute ici d'autres paramètres selon tes besoins
