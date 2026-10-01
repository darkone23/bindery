{
  description = "bindery — book-reprint toolkit (M0 ingest, M1 trim+impose)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f (import nixpkgs { inherit system; }));
    in
    {
      packages = forAll (
        pkgs:
        let
          binderyBin = pkgs.writers.writePython3Bin "bindery"
            {
              flakeIgnore = [ "E501" "E265" ];
              libraries = ps: [ ps.reportlab ps.pillow ];
            } ./bindery.py;
        in
        rec {
          default = bindery;
          bindery = pkgs.symlinkJoin {
            name = "bindery-0.2.0";
            paths = [ binderyBin ];
            nativeBuildInputs = [ pkgs.makeWrapper ];
            postBuild = ''
              wrapProgram $out/bin/bindery --prefix PATH : ${pkgs.poppler-utils}/bin \
                --set BINDERY_FONT_DIR ${pkgs.dejavu_fonts}/share/fonts/truetype
            '';
          };
        }
      );

      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [
            self.packages.${pkgs.system}.default
            (pkgs.python3.withPackages (ps: [
              ps.pytest
              ps.reportlab
              ps.pillow
            ]))
            pkgs.poppler-utils
            pkgs.just
            pkgs.dejavu_fonts
          ];
          # apparatus-leaf fonts (HOL-256 M3)
          shellHook = ''
            export BINDERY_FONT_DIR=${pkgs.dejavu_fonts}/share/fonts/truetype
          '';
        };
        # M2 structure stage (HOL-255): docling layout + tesseract OCR run
        # in the stage's devenv (devenv.nix / devenv.yaml, `devenv shell`) —
        # the impure/unfree business lives there, not in this flake, which
        # stays unfree-clean.
        # M4b typeset stage (HOL-259): WeasyPrint (Pango shapes Devanagari)
        # + Lohit Devanagari; FONTCONFIG_FILE is set declaratively — bare
        # nix shells do not scan host fonts (spike lesson, run 3).
        typeset = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (ps: [
              ps.weasyprint
              ps.pytest
            ]))
            pkgs.lohit-fonts.devanagari
            pkgs.dejavu_fonts
            pkgs.poppler-utils
            pkgs.just
          ];
          FONTCONFIG_FILE = pkgs.makeFontsConf {
            fontDirectories = [
              pkgs.lohit-fonts.devanagari
              pkgs.dejavu_fonts
            ];
          };
        };
      });

      checks = forAll (
        pkgs:
        let
          pytestEnv = pkgs.python3.withPackages (ps: [
            ps.pytest
            ps.reportlab
            ps.pillow
          ]);
          typesetEnv = pkgs.python3.withPackages (ps: [
            ps.weasyprint
            ps.pytest
          ]);
          fontConf = pkgs.makeFontsConf {
            fontDirectories = [ pkgs.lohit-fonts.devanagari pkgs.dejavu_fonts ];
          };
        in
        {
          default = pkgs.runCommand "bindery-pytest"
            {
              nativeBuildInputs = [
                pytestEnv
                pkgs.poppler-utils
                pkgs.dejavu_fonts
              ];
            }
            ''
              export BINDERY_FONT_DIR=${pkgs.dejavu_fonts}/share/fonts/truetype
              cp -r ${self} src
              chmod -R u+w src
              cd src
              ${pytestEnv}/bin/pytest -q tests
              touch $out
            '';
          # M4b typeset stage (HOL-259): render smoke through the real
          # WeasyPrint -> raster -> manifest pipeline on the mini fixture.
          typeset = pkgs.runCommand "bindery-typeset-pytest"
            {
              nativeBuildInputs = [
                typesetEnv
                pkgs.poppler-utils
                pkgs.lohit-fonts.devanagari
                pkgs.dejavu_fonts
              ];
              FONTCONFIG_FILE = fontConf;
            }
            ''
              cp -r ${self} src
              chmod -R u+w src
              cd src
              ${typesetEnv}/bin/pytest -q tests/test_uttara_typeset.py
              touch $out
            '';
        }
      );
    };
}
