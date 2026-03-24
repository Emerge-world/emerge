analytics: analytics-install
	npx concurrently \
	  "uv run dashboard/analytics/backend/main.py" \
	  "cd dashboard/analytics/frontend && npm run dev"

analytics-install:
	cd dashboard/analytics/frontend && npm install

analytics-backend:
	uv run dashboard/analytics/backend/main.py

analytics-frontend:
	cd dashboard/analytics/frontend && npm run dev
