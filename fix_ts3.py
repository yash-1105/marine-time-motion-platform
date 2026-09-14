with open("apps/web/src/app/ingestion/page.tsx", "r") as f:
    text = f.read()

text = text.replace("!can(\"create\", \"vessel_call\")", "!can(\"create:vessel_call\")")

with open("apps/web/src/app/ingestion/page.tsx", "w") as f:
    f.write(text)
