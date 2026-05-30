# Setting up a Google Maps Platform API key

We use Google as the **paid fallback** in our hybrid geocoding pipeline (free Nominatim is
tried first): place → coordinates (Geocoding), place details like ratings / hours / price
(Places), and transit/driving times (Routes/Directions).

> Needed starting in **Phase 2**. You can skip this until then.

## Steps
1. Sign in at <https://console.cloud.google.com/>.
2. **Create a project** (top bar → project dropdown → *New Project*), e.g. `trip-planner`.
3. **Enable billing** (APIs require a billing account). Google Maps Platform includes a
   recurring monthly free allotment — see current pricing at
   <https://mapsplatform.google.com/pricing/>. A single trip's geocoding usage is normally
   well within it. *(Pricing/free-tier terms change; check the page rather than trusting a
   number quoted here.)*
4. **Enable the APIs** — *APIs & Services → Library*, enable:
   - **Geocoding API**
   - **Places API (New)**
   - **Routes API** (or **Directions API**)
5. **Create the key** — *APIs & Services → Credentials → Create credentials → API key*.
6. **Restrict the key** (recommended) — edit the key → *API restrictions* → limit to the three
   APIs above; optionally add an *Application restriction* (server IP) once we deploy.
7. **Save it** to `.env`:
   ```
   GOOGLE_MAPS_API_KEY=AIza...
   ```

`.env` is gitignored — the key never gets committed.
