with open("apps/web/src/app/ingestion/page.tsx", "r") as f:
    text = f.read()

text = text.replace("const { principal } = useAuth();", "const { can, roles } = useAuth();")
text = text.replace("!principal?.permissions.includes(\"create:vessel_call\")", "!can(\"create\", \"vessel_call\")")
text = text.replace("principal.roles.includes(\"Platform Administrator\") || principal.roles.includes(\"Developer\")", "roles.includes(\"Platform Administrator\") || roles.includes(\"Developer\")")

with open("apps/web/src/app/ingestion/page.tsx", "w") as f:
    f.write(text)
