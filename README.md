# 📚 Chatbot GLPI Crédit Mutuel du Sénégal

## 1. Présentation
Ce projet met en place un agent conversationnel intelligent (chatbot) connecté à GLPI, destiné à automatiser le support technique du Crédit Mutuel du Sénégal (CMS). Il permet la création, le suivi, la suppression, la relance et la recherche de tickets, tout en respectant strictement les droits utilisateurs (admin, support, client, etc.).

---

## 2. Fonctionnalités principales
- **Authentification sécurisée** (JWT, gestion de session)
- **Détection d’intention** via LLM (Ollama, prompt dédié)
- **Gestion complète des tickets GLPI** : création, suivi, suppression, relance, recherche
- **Filtrage intelligent** : chaque utilisateur ne voit que ses tickets (sauf support/admin)
- **Logs d’audit** (MongoDB)
- **Rôles** : admin, agent support, support, client
- **Respect du canevas GLPI** (détection doublons, tickets incomplets, etc.)

---

## 3. Rôles et droits
| Rôle           | Droits principaux                                                                 |
|----------------|----------------------------------------------------------------------------------|
| admin          | Accès total à tous les tickets, gestion des rôles, configuration                  |
| agent support  | Accès à tous les tickets, gestion avancée, alertes, rapports                     |
| support        | Accès à tous les tickets, relances, rapports                                     |
| client         | Accès uniquement à ses tickets, création/suivi/suppression/relance de ses tickets|

- Le mapping user MCP ↔ GLPI est géré automatiquement.
- Les droits sont vérifiés à chaque action (listing, suppression, suivi, etc.).

---

## 4. Workflow LLM (détection d’intention)
- **Prompt** : voir `intent_llm_prompt.md`
- **Intents supportés** :
    - create_ticket
    - list_tickets
    - search_ticket
    - update_ticket
    - delete_ticket
    - get_ticket_status
    - remind_ticket
    - unknown
- **Exemple** :
    - « Je veux créer un ticket pour un problème de connexion » → `create_ticket`
    - « Où en est le ticket 35 ? » → `get_ticket_status`
    - « Supprime le ticket 12 » → `delete_ticket`

---

## 5. Endpoints principaux
- `/ai/chatbot/ask` : point d’entrée unique, reçoit la question utilisateur, retourne la réponse adaptée
- `/glpi/ticket/*` : gestion fine des tickets (CRUD, statut, relance)

---

## 6. Procédures d’installation et de configuration
1. **Cloner le repo**
2. **Installer les dépendances** :
   ```bash
   pip install -r requirements.txt
   ```
3. **Configurer** :
   - GLPI REST API (localhost:8080)
   - MongoDB (pour logs)
   - Ollama (LLM local)
   - Variables d’environnement (tokens, etc.)
4. **Lancer le backend** :
   ```bash
   uvicorn main:app --reload
   ```
5. **Tester avec cURL ou Postman**

---

## 7. Procédures de sauvegarde et rollback
- Sauvegarder la base de données GLPI et MongoDB avant toute modification majeure
- Sauvegarder les fichiers modifiés (code, config)
- Tenir un journal des modifications (voir dossier `logs/` ou MongoDB)
- Pour rollback : restaurer la base et les fichiers sauvegardés

---

## 8. Désactivation des logs de debug (production)
- Dans `routers/glpi.py` et autres modules, commenter ou supprimer les `print` ou logs de debug avant passage en prod.
- Vérifier qu’aucune information sensible n’est loguée.

---

## 9. Scénarios d’usage (extraits)
- **Création ticket** :
    - « Mon imprimante ne fonctionne plus » → création guidée, vérification des champs, ticket créé, numéro retourné
- **Détection doublon** :
    - « J’ai déjà signalé ce problème » → le bot propose le ticket existant
- **Suivi ticket** :
    - « Où en est le ticket 35 ? » → statut retourné si droits OK
- **Relance** :
    - « Relance le ticket 35 » → relance automatique si droits OK

---

## 10. Bonnes pratiques
- Ne modifier qu’un seul composant à la fois
- Toujours garder une copie de sauvegarde avant modification
- Ajouter des commentaires explicatifs
- Tester chaque modification individuellement
- Documenter chaque évolution

---

## 11. Tests automatisés (à compléter)
- Prévoir des tests unitaires pour chaque endpoint critique (création, suppression, suivi, etc.)
- Prévoir un test d’intégration sur le flux principal (question → intent → action GLPI → réponse)
- Vérifier le respect des droits par rôle

---

## 12. Contact
Pour toute question ou évolution, contacter l’équipe projet CMS ou le responsable technique.

---

**Projet validé pour livraison après vérification de cette documentation et désactivation des logs de debug.**
