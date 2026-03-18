import os
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("JSearch Connector")


def detect_country(location: str) -> str | None:
    loc = location.lower().strip()

    if "france" in loc or "paris" in loc:
        return "fr"
    if "germany" in loc or "berlin" in loc or "allemagne" in loc:
        return "de"
    if "uk" in loc or "london" in loc or "england" in loc or "royaume-uni" in loc:
        return "gb"
    if "tunis" in loc or "tunisia" in loc or "tunisie" in loc:
        return "tn"
    if "spain" in loc or "madrid" in loc or "espagne" in loc:
        return "es"

    return None


@mcp.tool()
async def search_jobs(
    query: str,
    location: str = "",
    remote_jobs_only: bool = False,
) -> str:
    """
    Recherche des offres d'emploi en temps réel via l'API JSearch.
    """

    api_key = os.environ.get("JSEARCH_API_KEY")
    if not api_key:
        return "Erreur : la variable d'environnement JSEARCH_API_KEY n'est pas configurée."

    search_query = query.strip()
    if location.strip():
        search_query += f" in {location.strip()}"
    if remote_jobs_only:
        search_query += " remote"

    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "jsearch.p.rapidapi.com",
    }
    params = {
        "query": search_query,
        "page": "1",
        "num_pages": "1",
    }

    country_code = detect_country(location)
    if country_code:
        params["country"] = country_code

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()

        jobs = payload.get("data", [])
        if not jobs:
            return f"Aucune offre d'emploi trouvée pour la recherche : '{search_query}'"

        results = []
        for job in jobs[:5]:
            title = job.get("job_title", "Titre inconnu")
            employer = job.get("employer_name", "Employeur inconnu")
            apply_link = (
                job.get("job_apply_link")
                or job.get("job_google_link")
                or "Lien non disponible"
            )

            desc = (job.get("job_description") or "").strip()
            if not desc:
                desc = "Aucune description fournie."
            elif len(desc) > 500:
                desc = desc[:497] + "..."

            city = job.get("job_city", "")
            country = job.get("job_country", "")
            loc = f"{city}, {country}".strip(" ,") or "Lieu non précisé"

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
        return f"Erreur API JSearch ({e.response.status_code}) : {e.response.text}"
    except Exception as e:
        return f"Erreur inattendue : {str(e)}"


app = mcp.sse_app()
