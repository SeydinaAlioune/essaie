from fastapi import APIRouter, HTTPException, Query, Body, Depends
from typing import Optional
from db import get_database
from datetime import datetime
from routers.auth import get_current_user
from routers.admin import require_role

# Connexion à la base MongoDB  accès à la collection "documents"
db = get_database()
#permet l'accès à la collection "documents"
documents_collection = db["documents"]

router = APIRouter()


@router.get("/docs/search")
def search_documents(
    id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user=Depends(get_current_user)
):
    # Recherche accessible à tous les utilisateurs connectés, mais filtrage selon roles_allowed
    user_role = getattr(current_user, "role", None)
    if id is not None:
        doc = documents_collection.find_one({"id": id}, {"_id": 0})
        if doc and user_role in doc.get("roles_allowed", ["admin", "agent support", "client"]):
            return [doc]
        return []
    query = {}
    if keyword:
        query["$or"] = [
            {"title": {"$regex": keyword, "$options": "i"}},
            {"content": {"$regex": keyword, "$options": "i"}}
        ]
    if category:
        query["category"] = {"$regex": f"^{category}$", "$options": "i"}
    cursor = documents_collection.find(query, {"_id": 0}).skip(skip).limit(limit)
    docs = [doc for doc in cursor if user_role in doc.get("roles_allowed", ["admin", "agent support", "client"])]
    return docs

@router.post("/docs/create")
def create_document(
    title: str = Body(...),
    content: str = Body(...),
    category: str = Body(...),
    roles_allowed: list = Body(["admin", "agent support", "client"]),
    current_user=Depends(require_role("admin"))
):
    """
    Crée un nouveau document (admin). 'roles_allowed' détermine qui peut le voir.
    """
    last_doc = documents_collection.find_one(sort=[("id", -1)])
    new_id = last_doc["id"] + 1 if last_doc else 1
    date_creation = datetime.utcnow().isoformat()
    new_doc = {"id": new_id, "title": title, "content": content, "category": category, "date_creation": date_creation, "roles_allowed": roles_allowed}
    documents_collection.insert_one(new_doc)
    doc = documents_collection.find_one({"id": new_id}, {"_id": 0})
    return doc

@router.put("/docs/update/{doc_id}")
def update_document(
    doc_id: int,
    title: Optional[str] = Body(None),
    content: Optional[str] = Body(None),
    category: Optional[str] = Body(None),
    roles_allowed: Optional[list] = Body(None),
    current_user=Depends(require_role("admin"))
):
    """
    Met à jour un document existant (admin). Peut modifier les rôles autorisés.
    """
    update_fields = {}
    if title is not None:
        update_fields["title"] = title
    if content is not None:
        update_fields["content"] = content
    if category is not None:
        update_fields["category"] = category
    if roles_allowed is not None:
        update_fields["roles_allowed"] = roles_allowed
    if not update_fields:
        raise HTTPException(status_code=400, detail="Aucune donnée à mettre à jour.")
    result = documents_collection.update_one(
        {"id": doc_id},
        {"$set": update_fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Document non trouvé")
    doc = documents_collection.find_one({"id": doc_id}, {"_id": 0})
    return doc

@router.delete("/docs/{doc_id}")
def delete_document(doc_id: int, current_user=Depends(require_role("admin"))):
    """
    Supprime un document par son id (admin).
    """
    deleted_doc = documents_collection.find_one_and_delete({"id": doc_id}, projection={"_id": 0})
    if deleted_doc:
        return {"message": "Document supprimé", "document": deleted_doc}
    raise HTTPException(status_code=404, detail="Document non trouvé")