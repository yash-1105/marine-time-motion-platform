import os
from apps.api.models import Base

def generate_erd():
    lines = ["# Entity Relationship Diagram", "", "```mermaid", "erDiagram"]
    
    for mapper in Base.registry.mappers:
        table = mapper.local_table
        schema = table.schema if table.schema else "public"
        table_name = f"{schema}.{table.name}"
        
        lines.append(f"    {schema}_{table.name} {{")
        for column in table.columns:
            pk = " PK" if column.primary_key else ""
            fk = " FK" if column.foreign_keys else ""
            lines.append(f"        {column.type.__class__.__name__} {column.name}{pk}{fk}")
        lines.append("    }")
        
        for fk in table.foreign_key_constraints:
            ref_table = fk.referred_table
            ref_schema = ref_table.schema if ref_table.schema else "public"
            lines.append(f"    {schema}_{table.name} ||--o{{ {ref_schema}_{ref_table.name} : references")
            
    lines.append("```")
    
    with open("docs/erd.md", "w") as f:
        f.write("\\n".join(lines))

def generate_data_dictionary():
    lines = ["# Data Dictionary", ""]
    
    for mapper in Base.registry.mappers:
        table = mapper.local_table
        schema = table.schema if table.schema else "public"
        lines.append(f"## {schema}.{table.name}")
        lines.append("")
        lines.append("| Column | Type | Nullable | Primary Key | Foreign Key |")
        lines.append("|---|---|---|---|---|")
        
        for column in table.columns:
            nullable = "Yes" if column.nullable else "No"
            pk = "Yes" if column.primary_key else "No"
            fk = "Yes" if column.foreign_keys else "No"
            lines.append(f"| {column.name} | {column.type} | {nullable} | {pk} | {fk} |")
        
        lines.append("")
        
    with open("docs/data-dictionary.md", "w") as f:
        f.write("\\n".join(lines))

if __name__ == "__main__":
    generate_erd()
    generate_data_dictionary()
    print("ERD and Data Dictionary generated.")
