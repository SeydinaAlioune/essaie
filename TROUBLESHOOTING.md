# Journal de Dépannage

Ce fichier documente les problèmes complexes rencontrés et leurs solutions.

## Problème : Erreur de permission lors de l'ajout d'un suivi à un ticket GLPI

**Date :** 20/07/2025

### Symptômes

Lors de la tentative d'ajout d'un suivi (commentaire) à un ticket existant depuis l'application mobile, l'API backend retournait systématiquement une erreur `400 Bad Request`.

Le message d'erreur détaillé était :
```json
{
  "detail": "Erreur GLPI: [\"ERROR_GLPI_ADD\",\"Vous n'avez pas les droits requis pour réaliser cette action.\"]"
}
```

Ce message était trompeur, car le problème ne venait pas réellement des permissions de l'utilisateur ou des tokens d'API, mais de la manière dont la requête était construite.

### Cause Racine

Le problème se situait dans la fonction `glpi_add_followup` du fichier `routers/glpi.py`.

Le corps (payload) de la requête `POST` envoyée à l'endpoint `/ITILFollowup` de l'API GLPI était incorrect.

**Ancien code (incorrect) :**
```python
payload = {
    "input": {
        "tickets_id": ticket_id,  # Incorrect
        "content": agent_content,
        "is_private": 1 if is_private else 0
    }
}
```

L'API GLPI ne reconnaît pas le champ `tickets_id` dans ce contexte. La documentation officielle spécifie que pour lier un suivi à un ticket, il faut utiliser deux champs distincts : `itemtype` et `items_id`.

### Solution

La solution a été de corriger la structure du payload pour qu'elle soit conforme à la documentation de l'API GLPI.

**Nouveau code (corrigé) :**
```python
payload = {
    "input": {
        "itemtype": "Ticket",      # Correct : Spécifie que l'objet est un Ticket
        "items_id": ticket_id,       # Correct : Spécifie l'ID du ticket
        "content": agent_content,
        "is_private": 1 if is_private else 0
    }
}
```

Cette modification a résolu le problème et a permis d'ajouter des suivis aux tickets avec succès.
