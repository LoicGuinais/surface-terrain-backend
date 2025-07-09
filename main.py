from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import geopandas as gpd
import gzip, json, os, requests, io

app = FastAPI()

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
def get_parcelles(code_postal: str, min: int = 0, max: int = 1000, limit: int = 100):
    matches = df_postaux[df_postaux["code_postal"] == code_postal]
    if matches.empty:
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
            return {"error": f"Erreur pour {row['nom_de_la_commune']}: {e}"}

    return {
        "type": "FeatureCollection",
        "features": all_features
    }
