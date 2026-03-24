analytics: analytics-install
	npx concurrently \
	  "uv run python -m dashboard.analytics.backend.main" \
	  "cd dashboard/analytics/frontend && npm run dev"

analytics-install:
	cd dashboard/analytics/frontend && npm install

analytics-backend:
	uv run python -m dashboard.analytics.backend.main

analytics-frontend:
	cd dashboard/analytics/frontend && npm run dev
