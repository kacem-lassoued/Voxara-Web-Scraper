# Price Comparison MVP

This repository keeps the existing scraper code and adds a small FastAPI backend plus a Next.js frontend around it.

The goal is an MVP only:

1. Keep the scraper in [scraper/](scraper).
2. Store scraped products and prices in PostgreSQL.
3. Serve data through FastAPI.
4. Render a small product comparison site in Next.js.

## Current structure

```text
.
├── backend/
│   ├── app/
│   │   ├── config.py
│   │   ├── crud.py
│   │   ├── database.py
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── routers/
│   │       └── products.py
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── compare/[productName]/page.tsx
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── products/[id]/page.tsx
│   ├── components/
│   │   ├── ComparisonTable.tsx
│   │   └── ProductCard.tsx
│   └── lib/
│       └── api.ts
├── scraper/
├── README.md
└── .gitignore
```

## Backend

Backend stack:

- FastAPI
- SQLAlchemy
- PostgreSQL
See [backend/README.md](backend/README.md) for the full backend setup (Alembic + async).
- CORS enabled
- Environment variables through `DATABASE_URL` and `BACKEND_CORS_ORIGINS`

API routes:

- `GET /products`
- `GET /products/{id}`
- `GET /products/{id}/history`
- `GET /search?q=...`
- `GET /compare/{product_name}`
- `POST /ingest`

## Frontend

Frontend stack:

- Next.js App Router
- Tailwind CSS
- Product cards
- Search bar
- Product comparison table
- Small fetch helper in `frontend/lib/api.ts`

## Setup

1. Create a PostgreSQL database named `price_compare`.
2. Update the root `.env.example` values and copy them to a local `.env` file if you want to use a single shared file for the backend.
3. Install backend packages:

```bash
pip install -r backend/requirements.txt
```

4. Start the FastAPI app:

```bash
uvicorn backend.app.main:app --reload
```

5. Install frontend packages:

```bash
cd frontend
npm install
```

6. Start the frontend:

```bash
npm run dev
```

7. Open `http://localhost:3000`.

## Ingest scraped data

The backend exposes a minimal ingestion endpoint for your scrapers. Send a list of items in JSON and the API will:

- upsert products by `name/title` + `brand`
- insert a new price row for every scrape (price history)

Example:

```bash
curl -X POST http://localhost:8000/ingest \
	-H "Content-Type: application/json" \
	-d '[
		{
			"title": "Asus VivoBook 15",
			"price": 1299.0,
			"image_url": "https://...",
			"item_url": "https://www.mytek.tn/...",
			"source": "mytek.tn"
		}
	]'
```

## How the scraper fits in

The existing scraper code stays in [scraper/](scraper) and can later insert or update rows in PostgreSQL. The backend and frontend are only scaffolding around that data flow.

## Next step after this scaffold

Add a small scraper-to-database write path that reuses the current scraper output format, then wire the frontend to real database rows.
