# Fixtures

One JSON per route, named `METHOD_path.json` (request and response where both matter). Lane B builds against these with `VITE_MOCK=1`; Lane A regenerates them from the running API so they never drift. Every aggregate carries `n`; nothing here has n < 5.
