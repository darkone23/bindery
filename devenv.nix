# M2 structure stage env (HOL-255): docling layout + tesseract OCR.
#
# The impure/unfree business of the structure stage lives HERE and only
# here (docling's saxonche dependency is unfree; first use downloads the
# docling layout models to ~/.cache/docling). The pure flake (nix build,
# pytest) never evaluates this file — allowUnfree in devenv.yaml is
# scoped to this environment.
{ pkgs, ... }: {
  packages = [
    (pkgs.python3.withPackages (ps: [
      ps.docling-slim
      ps.pillow
      ps.numpy
      ps.pytest
    ] ++ ps.docling-slim.optional-dependencies.convert-core
      ++ ps.docling-slim.optional-dependencies.format-pdf-docling
      ++ ps.docling-slim.optional-dependencies.models-local))
    pkgs.tesseract
    pkgs.poppler-utils
    pkgs.just
  ];

  enterShell = ''
    # docling layout models live in ~/.cache/docling (downloaded once;
    # network only needed on that first run)
  '';
}