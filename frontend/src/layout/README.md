# Maintainable layout source

`layout.js` is the canonical source for the existing VuePress layout asset. Run:

```powershell
python scripts/build_layout.py
```

The build intentionally copies the ES module without bundling. Existing HTML pages continue to load
`frontend/dist/assets/layout.96d49288.js`, and that module continues to use the vendored
`app.547295de.js` runtime.

The source began as the recovered production bundle. Keep behavior changes here, use descriptive
names when touching an area, and regenerate the dist asset. Do not patch the generated asset.
