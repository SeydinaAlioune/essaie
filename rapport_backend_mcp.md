# Rapport Technique Complet — Backend FastAPI MCP

## 1. Introduction

Ce document explique, étape par étape, la logique, la structure, le code et le fonctionnement du backend MCP développé en FastAPI. Il est conçu pour être compréhensible par un binôme n’ayant jamais codé de backend.

---

## 2. Architecture Générale

### 2.1. Technologies utilisées
- **FastAPI** : framework web Python moderne pour créer des APIs REST.
- **MongoDB** : base de données NoSQL pour stocker utilisateurs, tickets, documents.
- **JWT** : pour l’authentification sécurisée.
- **bcrypt** : pour le hashage des mots de passe.
- **SMTP (Gmail)** : pour l’envoi de mails (mot de passe oublié).
- **Organisation du code** :
  - `routers/auth.py` : gestion des utilisateurs et de l’authentification.
  - `routers/admin.py` : endpoints réservés à l’admin.
  - `routers/glpi.py` : gestion des tickets/support.
  - `routers/docs.py` : gestion documentaire interne.

### 2.2. Structure des données principales

#### Utilisateurs (`users`)
| Champ      | Type    | Description                        |
|------------|---------|------------------------------------|
| id         | int/str | Identifiant unique                 |
| name       | str     | Nom complet                        |
| email      | str     | Email (unique)                     |
| password   | str     | Mot de passe hashé                 |
| role       | str     | Rôle (`admin`, `agent support`, `client`) |
| status     | str     | Statut (`active`, `pending`, `blocked`, `rejected`) |

#### Tickets
| Champ            | Type    | Description                  |
|------------------|---------|------------------------------|
| id               | int/str | Identifiant unique           |
| title            | str     | Titre du ticket              |
| content          | str     | Description                  |
| requester_email  | str     | Email du créateur            |
| ...              | ...     | Autres champs GLPI           |

#### Documents internes
| Champ         | Type    | Description                          |
|---------------|---------|--------------------------------------|
| id            | int     | Identifiant unique                   |
| title         | str     | Titre                                |
| content       | str     | Contenu                              |
| category      | str     | Catégorie                            |
| date_creation | str     | Date de création (ISO)               |
| roles_allowed | list    | Rôles autorisés à voir ce document   |

---

## 3. Gestion des utilisateurs et des rôles

### 3.1. Inscription et validation

- **Auto-inscription** via `/auth/register`  
  L’utilisateur fournit nom, email, mot de passe, rôle (`client` ou `agent support`).  
  Le compte est créé avec `status="pending"`, en attente de validation par un admin.

- **Validation par l’admin** via `/admin/validate-user/{email}`  
  L’admin valide le compte, qui passe à `status="active"`.

- **Connexion** via `/auth/login`  
  Vérifie l’email, le mot de passe (hashé), et que le compte est `active`.  
  Retourne un JWT (token) à utiliser pour toutes les requêtes protégées.

- **Modification de profil** via `/auth/update-me`  
  L’utilisateur connecté peut modifier son nom ou son mot de passe.

- **Mot de passe oublié**  
  - `/auth/request-password-reset` : génère un code envoyé par email (valide 15 min).
  - `/auth/reset-password` : l’utilisateur fournit l’email, le code, et le nouveau mot de passe.

#### Exemple de création d’utilisateur (extrait de code)
```python
@router.post("/auth/register")
def register(name: str, email: str, password: str, role: str):
    # Vérification du rôle
    allowed_roles = ["client", "agent support"]
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Rôle non autorisé")
    # Hash du mot de passe
    hashed_pw = hash_password(password)
    # Création du document utilisateur
    user_doc = {"name": name, "email": email, "password": hashed_pw, "role": role, "status": "pending"}
    users_collection.insert_one(user_doc)
    return {"message": "Inscription réussie, en attente de validation"}
```

### 3.2. Rôles et contrôle d’accès

- **admin** : tous les droits (validation, création, suppression, accès à tout)
- **agent support** : accès complet aux tickets, lecture des documents autorisés
- **client** : accès à ses propres tickets, lecture des documents autorisés

Le contrôle d’accès se fait par des dépendances FastAPI, par exemple :
```python
def require_role(role: str):
    def dependency(current_user: User = Depends(get_current_user)):
        if current_user.role != role:
            raise HTTPException(status_code=403, detail="Accès interdit")
        return current_user
    return dependency
```

---

## 4. Gestion des tickets

### 4.1. Création de ticket

- Endpoint : `/glpi/ticket/create` (POST)
- L’utilisateur connecté crée un ticket, son email est enregistré comme créateur (`requester_email`).

### 4.2. Consultation des tickets

- Endpoint : `/glpi/tickets` (GET)
- **admin/agent support** : voient tous les tickets
- **client** : ne voit que ses propres tickets

### 4.3. Modification/Suppression

- Endpoints : `/glpi/ticket/update/{ticket_id}` (PATCH), `/glpi/ticket/delete/{ticket_id}` (DELETE)
- Seul le créateur ou un admin/agent support peut modifier/supprimer.

#### Exemple de filtrage des tickets
```python
@router.get("/glpi/tickets")
def glpi_list_tickets(current_user: User = Depends(get_current_user)):
    tickets = get_all_tickets()
    if current_user.role not in ["admin", "agent support"]:
        tickets = [t for t in tickets if t["requester_email"] == current_user.email]
    return tickets
```

---

## 5. Gestion documentaire

### 5.1. Création/modification/suppression (admin uniquement)

- **Création** via `/docs/create` (POST)  
  L’admin peut définir les rôles autorisés (`roles_allowed`), la date de création est ajoutée automatiquement.

- **Mise à jour** via `/docs/update/{doc_id}` (PUT)  
  L’admin peut changer le titre, contenu, catégorie, rôles autorisés.

- **Suppression** via `/docs/{doc_id}` (DELETE)

### 5.2. Recherche/lecture (tous les utilisateurs connectés)

- **Recherche** via `/docs/search` (GET)  
  - Recherche par id, mot-clé, catégorie
  - Pagination (`skip`, `limit`)
  - Filtrage automatique : chaque utilisateur ne voit que les documents où son rôle est dans `roles_allowed`.

#### Exemple de filtrage documentaire
```python
@router.get("/docs/search")
def search_documents(..., current_user=Depends(get_current_user)):
    user_role = getattr(current_user, "role", None)
    docs = [doc for doc in documents_collection.find(query) if user_role in doc.get("roles_allowed", ["admin", "agent support", "client"])]
    return docs
```

---

## 6. Sécurité et bonnes pratiques

- **Hash des mots de passe** : jamais stockés en clair
- **JWT** : chaque requête protégée nécessite un token
- **Contrôle d’accès** : tous les endpoints critiques sont protégés par des dépendances
- **Statuts utilisateurs** : contrôle du workflow (pending, active, blocked…)

---

## 7. Workflow utilisateur (exemples concrets)

1. **Inscription** → **Validation admin** → **Connexion** → **Création ticket** → **Lecture docs**
2. **Mot de passe oublié** → **Réception code par mail** → **Réinitialisation**
3. **Admin** : création/modification/suppression utilisateurs, tickets, documents

---

## 8. Conseils pour lire le code et tester

- **Chaque module** (`auth.py`, `admin.py`, `glpi.py`, `docs.py`) est indépendant
- **Endpoints** : toujours décorés par `@router.<method>`
- **Dépendances** : `Depends(get_current_user)` pour vérifier l’authentification, `Depends(require_role("admin"))` pour limiter à l’admin
- **Tester avec Swagger UI** : http://localhost:8000/docs

---

## 9. Schéma d’architecture (optionnel)

```
[Utilisateur] --(HTTP)--> [FastAPI] --(requêtes)--> [MongoDB]
                |               |                  |
                |               |--(SMTP)--> [Gmail pour reset]
                |               |--(JWT)--> [Sécurité]
```

---

## 10. Conclusion

Ce backend est prêt à être utilisé, sécurisé, modulaire, et facilement extensible (IA, chatbot, etc.).  
Chaque partie est pensée pour être claire, logique, et maintenable.

---

**PMais ca reste encore on a pas encore integrer l'IA(LLM et Base vectorielle.Ceci englobe pour l'instant la gestion des users,des ticket et documentation)**
