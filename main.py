from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import geopandas as gpd
import gzip, hashlib, json, os, requests, io
from datetime import datetime

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SEARCH_TRACKING_IP_SALT = os.getenv("SEARCH_TRACKING_IP_SALT")
SEARCH_EVENTS_TABLE = "search_events"


def get_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    if request.client:
        return request.client.host

    return None


def hash_client_ip(ip_address: str | None) -> str | None:
    if not ip_address or not SEARCH_TRACKING_IP_SALT:
        return None

    value = f"{SEARCH_TRACKING_IP_SALT}:{ip_address}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def track_search_event(
    request: Request,
    *,
    code_postal: str,
    min_area: int,
    max_area: int,
    limit_requested: int,
    matched_communes: int,
    result_count: int | None,
    status: str,
    error_message: str | None = None,
) -> None:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return

    payload = {
        "code_postal": code_postal,
        "min_area": min_area,
        "max_area": max_area,
        "limit_requested": limit_requested,
        "matched_communes": matched_communes,
        "result_count": result_count,
        "status": status,
        "error_message": error_message,
        "request_path": request.url.path,
        "request_query": request.url.query,
        "referrer": request.headers.get("Referer"),
        "user_agent": request.headers.get("User-Agent"),
        "ip_hash": hash_client_ip(get_client_ip(request)),
    }

    try:
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/{SEARCH_EVENTS_TABLE}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=payload,
            timeout=3,
        )
        response.raise_for_status()
    except Exception as e:
        print(f"Search tracking failed: {e}")

# --- Middleware to log request metadata ---
@app.middleware("http")
async def log_request_metadata(request: Request, call_next):
    now = datetime.now().isoformat()
    ip_hash = hash_client_ip(get_client_ip(request)) or "N/A"
    ua = request.headers.get("User-Agent", "N/A")
    referer = request.headers.get("Referer", "N/A")
    print(f"[{now}] IP_HASH={ip_hash} | UA={ua} | REF={referer} | PATH={request.url.path} | QUERY={request.url.query}")
    return await call_next(request)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to ["https://surface-terrain.fr"] in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Load postal codes once ---
df_postaux = pd.read_csv("data/base-officielle-codes-postaux.csv", dtype=str)
df_postaux.columns = df_postaux.columns.str.strip()

# --- Main endpoint ---
@app.get("/parcelles")
def get_parcelles(
    request: Request,
    background_tasks: BackgroundTasks,
    code_postal: str,
    min: int = 0,
    max: int = 1000,
    limit: int = 100,
):
    matches = df_postaux[df_postaux["code_postal"] == code_postal]
    if matches.empty:
        background_tasks.add_task(
            track_search_event,
            request,
            code_postal=code_postal,
            min_area=min,
            max_area=max,
            limit_requested=limit,
            matched_communes=0,
            result_count=0,
            status="not_found",
            error_message="Code postal non trouvé",
        )
        return {"error": "Code postal non trouvé"}

    all_features = []

    for _, row in matches.iterrows():
        insee = row["code_commune_insee"]
        dept = insee[:2]
        filename = f"cadastre-{insee}-parcelles.json.gz"
        url = f"https://cadastre.data.gouv.fr/data/etalab-cadastre/2025-04-01/geojson/communes/{dept}/{insee}/{filename}"
        local_path = os.path.join("data", "cache", filename)

        # --- Make sure cache dir exists ---
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        try:
            # --- Use cached file if available ---
            if os.path.isfile(local_path):
                with gzip.open(local_path, "rt", encoding="utf-8") as f:
                    geojson_data = json.load(f)
            else:
                response = requests.get(url, timeout=20)
                response.raise_for_status()

                with open(local_path, "wb") as f:
                    f.write(response.content)

                with gzip.open(io.BytesIO(response.content), "rt", encoding="utf-8") as f:
                    geojson_data = json.load(f)

            gdf = gpd.GeoDataFrame.from_features(geojson_data["features"])
            gdf["contenance"] = pd.to_numeric(gdf["contenance"], errors="coerce")

            filtered = gdf[
                (gdf["contenance"] >= min) & (gdf["contenance"] <= max)
            ].head(limit)

            for _, parcel in filtered.iterrows():
                try:
                    geometry_json = json.loads(gpd.GeoSeries([parcel["geometry"]]).to_json())["features"][0]["geometry"]
                    centroid = parcel.geometry.centroid
                    feature = {
                        "type": "Feature",
                        "geometry": geometry_json,
                        "properties": {
                            "section": parcel.get("section"),
                            "numero": parcel.get("numero"),
                            "contenance": parcel.get("contenance"),
                            "centroid_lon": centroid.x,
                            "centroid_lat": centroid.y,
                        }
                    }

                    all_features.append(feature)
                except Exception as e:
                    print(f"❌ Error parsing feature: {e}")

        except Exception as e:
            background_tasks.add_task(
                track_search_event,
                request,
                code_postal=code_postal,
                min_area=min,
                max_area=max,
                limit_requested=limit,
                matched_communes=len(matches),
                result_count=None,
                status="error",
                error_message=f"Erreur pour {row['nom_de_la_commune']}: {e}",
            )
            return {"error": f"Erreur pour {row['nom_de_la_commune']}: {e}"}

    background_tasks.add_task(
        track_search_event,
        request,
        code_postal=code_postal,
        min_area=min,
        max_area=max,
        limit_requested=limit,
        matched_communes=len(matches),
        result_count=len(all_features),
        status="success",
    )

    return {
        "type": "FeatureCollection",
        "features": all_features
    }
