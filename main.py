import os
import httpx
from mcp.server.fastmcp import FastMCP

# Initialisation du serveur FastMCP
# FastMCP crée et gère nativement une instance FastAPI et le transport SSE
mcp = FastMCP("JSearch Connector")

@mcp.tool()
async def search_jobs(query: str, location: str = "", remote_jobs_only: bool = False) -> str:
    """
    Recherche des offres d'emploi en temps réel via l'API JSearch.
    
    Args:
        query: Le poste ou l'intitulé recherché (par exemple : 'Software Engineer', 'Data Scientist').
        location: La localisation souhaitée (par exemple : 'Paris', 'Berlin').
        remote_jobs_only: Si True, ne retourne que des offres en télétravail.
    """
    # Récupération de la clé API depuis les variables d'environnement
    api_key = os.environ.get("JSEARCH_API_KEY")
    if not api_key:
        return "Erreur : La variable d'environnement JSEARCH_API_KEY n'est pas configurée sur le serveur."
        
    # Construction intelligente de la requête (ajout de "in" pour aider l'API)
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
    
    # Paramètres de base
    params = {
        "query": search_query,
        "page": "1",
        "num_pages": "1"
    }

    # Détection intelligente du pays pour forcer la recherche en Europe/Afrique
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
        # Appel asynchrone à l'API JSearch avec httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=15.0)
            response.raise_for_status()
            data = response.json()
            
            jobs = data.get("data", [])
            if not jobs:
                return f"Aucune offre d'emploi trouvée pour la recherche : '{search_query}'"
                
            # Limitation à 5 résultats maximum pour ne pas saturer le contexte de l'IA (Perplexity)
            results = []
            for job in jobs[:5]:
                title = job.get("job_title", "Titre inconnu")
                employer = job.get("employer_name", "Employeur inconnu")
                # Extraire le lien pour postuler (soit direct, soit Google Jobs)
                apply_link = job.get("job_apply_link") or job.get("job_google_link") or "Lien non disponible"
                
                # Résumé limité à 500 caractères
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
                    
                # Formatage concis du résultat de l'offre
                job_text = (
                    f"Titre : {title}\n"
                    f"Employeur : {employer}\n"
                    f"Lieu : {loc}\n"
                    f"Lien pour postuler : {apply_link}\n"
                    f"Résumé : {desc}"
                )
                results.append(job_text)
                
            # Les résultats seront concaténés avec un séparateur clair
            return "\n\n---\n\n".join(results)
            
    except httpx.HTTPStatusError as e:
        return f"Erreur lors de l'appel à l'API JSearch (Code {e.response.status_code}): {e.response.text}"
    except Exception as e:
        return f"Erreur inattendue lors de la recherche : {str(e)}"

# /!\ Création de l'application ASGI compatible avec uvicorn /!\
# Cette méthode fonctionne parfaitement avec mcp==1.2.0
app = mcp.get_starlette_app()
