with open("apps/web/src/app/ingestion/page.tsx", "r") as f:
    text = f.read()

text = text.replace("catch (e) {", "catch (error) {\n      const e = error as Error;")

with open("apps/web/src/app/ingestion/page.tsx", "w") as f:
    f.write(text)
