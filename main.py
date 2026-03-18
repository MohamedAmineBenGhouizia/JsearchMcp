import os
import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.middleware.cors import CORSMiddleware
from typing import Sequence

# Initialisation du serveur MCP standard
mcp = Server("JSearch Connector")

# 1. Définition de l'outil pour que Perplexity sache qu'il existe
@mcp.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_jobs",
            description="Recherche des offres d'emploi en temps réel via l'API JSearch.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Le poste recherché (ex: 'Software Engineer')"
                    },
                    "location": {
                        "type": "string",
                        "description": "La localisation souhaitée (ex: 'Paris'). Laissez vide si non spécifié."
                    },
                    "remote_jobs_only": {
                        "type": "boolean",
                        "description": "Si True, ne retourne que des offres en télétravail."
                    }
                },
                "required": ["query"]
            }
        )
    ]

# 2. Exécution de l'outil quand Perplexity l'appelle
@mcp.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> Sequence[TextContent]:
    if name != "search_jobs":
        raise ValueError(f"Outil inconnu : {name}")

    if not arguments or "query" not in arguments:
        raise ValueError("L'argument 'query' est requis")

    query = arguments.get("query", "")
    location = arguments.get("location", "")
    remote_jobs_only = arguments.get("remote_jobs_only", False)

    api_key = os.environ.get("JSEARCH_API_KEY")
    if not api_key:
        return [TextContent(type="text", text="Erreur : JSEARCH_API_KEY non configurée.")]

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
    elif "uk" in loc_lower or "london" in loc_lower or "england" in loc_lower:
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
                return [TextContent(type="text", text=f"Aucune offre trouvée pour : '{search_query}'")]

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
                    f"Lien : {apply_link}\n"
                    f"Résumé : {desc}"
                )
                results.append(job_text)

            final_text = "\n\n---\n\n".join(results)
            return [TextContent(type="text", text=final_text)]

    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=f"Erreur API JSearch (Code {e.response.status_code})")]
    except Exception as e:
        return [TextContent(type="text", text=f"Erreur inattendue : {str(e)}")]


# --- CONFIGURATION SSE POUR UVICORN ---
sse_transport = SseServerTransport("/messages")

async def handle_sse(request: Request):
    """Gère la connexion initiale SSE"""
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as endpoint:
        await mcp.run(endpoint, mcp.create_initialization_options(), request.scope)

async def handle_messages(request: Request):
    """Reçoit les messages de Perplexity"""
    await sse_transport.handle_post_message(
        request.scope, request.receive, request._send
    )

app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Route("/messages", endpoint=handle_messages, methods=["POST"]),
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
