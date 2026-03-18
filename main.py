import os
import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.middleware.cors import CORSMiddleware

# Initialisation du serveur MCP standard (pas FastMCP, pour éviter les erreurs d'attribut)
mcp = Server("JSearch Connector")

@mcp.tool()
async def search_jobs(query: str, location: str = "", remote_jobs_only: bool = False) -> str:
    """
    Recherche des offres d'emploi en temps réel via l'API JSearch.
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

# --- CONFIGURATION DU SERVEUR SSE POUR UVICORN / RENDER ---
sse_transport = SseServerTransport("/messages")

async def handle_sse(request: Request):
    """Gère la connexion initiale SSE que Perplexity va appeler sur /sse"""
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as endpoint:
        await mcp.run(endpoint, mcp.create_initialization_options(), request.scope)

async def handle_messages(request: Request):
    """Reçoit les messages JSON-RPC de Perplexity sur /messages"""
    await sse_transport.handle_post_message(
        request.scope, request.receive, request._send
    )

# Création de l'application ASGI compatible avec uvicorn
app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Route("/messages", endpoint=handle_messages, methods=["POST"]),
    ]
)

# Autoriser Perplexity à se connecter (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Ou spécifier "https://www.perplexity.ai" pour plus de sécurité
    allow_methods=["*"],
    allow_headers=["*"],
)
