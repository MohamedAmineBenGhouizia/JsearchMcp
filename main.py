import os
import httpx
import inspect
from mcp.server.fastmcp import FastMCP

# Initialisation du serveur FastMCP
mcp = FastMCP("JSearch Connector")

@mcp.tool()
async def search_jobs(query: str, location: str = "", remote_jobs_only: bool = False) -> str:
    """
    Interroge l'API JSearch pour trouver des offres d'emploi.
    
    Args:
        query: Le mot-clé de recherche (ex: 'Python developer', 'Data Scientist')
        location: Le lieu de recherche optionnel (ex: 'Paris', 'Remote', 'London')
        remote_jobs_only: Si True, retourne uniquement des offres en télétravail.
    """
    api_key = os.environ.get("JSEARCH_API_KEY")
    if not api_key:
        return "Erreur : La variable d'environnement JSEARCH_API_KEY n'est pas configurée sur le serveur."
        
    search_query = query.strip()
    if location:
        search_query += f" in {location.strip()}"
    if remote_jobs_only:
        search_query += " remote"
        
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "jsearch.p.rapidapi.com"
    }
    
    params = {
        "query": search_query,
        "page": "1",
        "num_pages": "1"
    }

    # Optimisation des recherches par pays, optionnelle mais pratique pour des requêtes génériques
    loc_lower = location.lower()
    if "france" in loc_lower or "paris" in loc_lower:
        params["country"] = "fr"
    elif "germany" in loc_lower or "berlin" in loc_lower or "allemagne" in loc_lower:
        params["country"] = "de"
    elif "uk" in loc_lower or "london" in loc_lower or "england" in loc_lower or "royaume-uni" in loc_lower:
        params["country"] = "gb"
    elif "tunis" in loc_lower:
        params["country"] = "tn"
    elif "spain" in loc_lower or "madrid" in loc_lower or "espagne" in loc_lower:
        params["country"] = "es"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=15.0)
            response.raise_for_status()
            data = response.json()
            
            jobs = data.get("data", [])
            if not jobs:
                return f"Aucune offre d'emploi trouvée pour la recherche : '{search_query}'"
                
            results = []
            # On retourne les 5 premières annonces pour ne pas saturer le contexte LLM.
            for job in jobs[:5]:
                title = job.get("job_title", "Titre inconnu")
                employer = job.get("employer_name", "Employeur inconnu")
                apply_link = job.get("job_apply_link") or job.get("job_google_link") or "Lien non disponible"
                
                desc = job.get("job_description", "")
                if desc and len(desc) > 500:
                    desc = desc[:497] + "..."
                elif not desc:
                    desc = "Aucune description fournie."
                    
                city = job.get("job_city", "")
                country = job.get("job_country", "")
                loc = f"{city}, {country}".strip(" ,")
                if not loc:
                    loc = "Lieu non précisé"
                    
                job_text = (
                    f"Titre : {title}\n"
                    f"Employeur : {employer}\n"
                    f"Lieu : {loc}\n"
                    f"Lien pour postuler : {apply_link}\n"
                    f"Résumé : {desc}"
                )
                results.append(job_text)
                
            return "\n\n---\n\n".join(results)
            
    except httpx.HTTPStatusError as e:
        return f"Erreur de l'API JSearch (Code {e.response.status_code}): {e.response.text}"
    except Exception as e:
        return f"Erreur inattendue : {str(e)}"

# ==============================================================================
# HACK INFAILLIBLE : EXPOSITION DE L'APPLICATION ASGI (STARLETTE/FASTAPI)
# ==============================================================================
# Les récentes versions du SDK natif (mcp >= 1.26.x) ont modifié plusieurs comportements:
# 1. get_starlette_app() a été supprimé ou renommé.
# 2. connect_sse est parfois renvoyé comme `tuple` (causant TypeError en async context).
# 3. Les applications sont parfois cachées dans des attibuts privés.
# Ce getter dynamique balaie et essaie tous les points de montage asgi.

def get_mcp_asgi_app(mcp_instance):
    """
    Extrait dynamiquement l'application ASGI compatible Starlette depuis une instance FastMCP.
    Résout définitivement l'erreur "AttributeError: 'FastMCP' object has no attribute 'get_starlette_app'".
    """
    
    # 1. Utilisation native ou recommandée par certaines versions :
    if hasattr(mcp_instance, "get_starlette_app"):
        return mcp_instance.get_starlette_app()
    
    if hasattr(mcp_instance, "get_asgi_app"):
        return mcp_instance.get_asgi_app()
    
    if hasattr(mcp_instance, "create_sse_app"):
        return mcp_instance.create_sse_app()
        
    # 2. Fouille approfondie des sous-composants souvent injectés par la bibliothèque récente :
    if hasattr(mcp_instance, "_mcp_server"):
        inner = mcp_instance._mcp_server
        if hasattr(inner, "get_asgi_app"):
            return inner.get_asgi_app()
        if hasattr(inner, "get_starlette_app"):
            return inner.get_starlette_app()
            
    # 3. Accès direct à la propriété privée de l'application (fallback classique) :
    if hasattr(mcp_instance, "_app"):
        return mcp_instance._app
        
    # 4. Fallback de dernière chance si l'instance FastMCP elle-même implémente __call__ ASGI :
    if callable(mcp_instance):
        try:
            sig = inspect.signature(mcp_instance.__call__)
            # Un ASGI a la signature (scope, receive, send)
            if len(sig.parameters) >= 3:
                return mcp_instance
        except Exception:
            pass
            
    # 5. Si vraiment tout a échoué, on génère un message qui nous donnera les bons attributs dans les logs de Render.
    available_attrs = dir(mcp_instance)
    raise RuntimeError(
        f"Impossible d'extraire l'application ASGI pour uvicorn.\n"
        f"Attributs disponibles sur l'instance : {available_attrs}\n\n"
        f"Désolé, la structure interne de mcp/FastMCP a encore muté."
    )

# L'application Uvicorn s'accroche enfin de manière sécurisée ici
app = get_mcp_asgi_app(mcp)
