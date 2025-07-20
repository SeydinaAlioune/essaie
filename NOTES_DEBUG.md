# Notes de Débogage - Authentification et Erreurs 401

Ce document résume les problèmes courants rencontrés et leurs solutions lors du développement de l'application.

## Problème 1 : Erreurs 401 "Unauthorized" persistantes sur le Frontend

Même après une connexion réussie, les appels aux routes protégées de l'API échouent avec une erreur 401.

### Cause Racine

Il y a deux causes principales qui se combinent :

1.  **Code Frontend Incorrect :** Le code de l'application (fichiers `.tsx`) utilise une mauvaise clé pour récupérer le token d'authentification depuis `AsyncStorage`. Par exemple, il cherche `'userToken'` alors que le token est sauvegardé sous la clé `'token'`.

2.  **Cache du Serveur Metro :** Le serveur de développement de React Native (Metro) garde en cache les anciennes versions des fichiers. Même si le code est corrigé, l'application continue d'utiliser l'ancienne version boguée.

### Solution en 2 Étapes

1.  **Vérifier le Code :** S'assurer que TOUS les appels à `AsyncStorage.getItem` pour récupérer le token utilisent la bonne clé. 
    - **Mauvais :** `AsyncStorage.getItem('userToken')`
    - **Correct :** `AsyncStorage.getItem('token')`

2.  **Vider le Cache Metro :** Arrêter le serveur Metro et le redémarrer avec la commande suivante à la racine du projet React Native (`CmsMobileApp`) :
    ```bash
    npx react-native start --reset-cache
    ```

3.  **Redémarrer l'Application :** Fermer complètement l'application sur l'émulateur/téléphone et la relancer.

---

## Problème 2 : Erreur 500 "Internal Server Error" sur le Backend

Le serveur FastAPI plante parfois, notamment lors de la connexion ou de la récupération de listes d'utilisateurs.

### Cause Racine

Incohérences entre les données stockées en base de données (MongoDB) et le format attendu par les schémas Pydantic.

- **Exemple 1 :** Un rôle utilisateur est stocké comme `"agent support"` (avec espace) au lieu de `"agent_support"` (avec underscore).
- **Exemple 2 :** Un document utilisateur n'a pas de champ `"password"`, ce qui fait planter la logique de vérification.

### Solution

Rendre le code du backend plus robuste pour qu'il nettoie ou valide les données avant de les passer aux schémas Pydantic. Nous avons ajouté des vérifications dans `routers/admin.py` et `routers/auth.py` pour gérer ces cas.
