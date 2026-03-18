import os
import httpx
from mcp.server.fastmcp import FastMCP

# On initialise le serveur
mcp = FastMCP("JSearch Connector")

@mcp.tool()
async def search_jobs(query: str, location: str = "", remote_jobs_only: bool = False) -> str:
    # Récupération clé API
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

# /!\ IL N'Y A PLUS DE VARIABLE 'app' ICI /!\
