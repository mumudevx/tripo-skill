"""Fix kit for Blender scripts: parametric, bbox-relative mesh operators.

    from fixkit import normals      # NormalKeeper: keep Tripo's custom normals (B7)
    from fixkit import ops          # recipe operators (OPS), run by apply_recipe.py

Every edit to a Tripo mesh runs inside `normals.NormalKeeper`; normals are never
recomputed across the whole mesh.
"""
