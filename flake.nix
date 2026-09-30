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
              wrapProgram $out/bin/bindery --prefix PATH : ${pkgs.poppler-utils}/bin
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
          ];
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
        in
        {
          default = pkgs.runCommand "bindery-pytest"
            {
              nativeBuildInputs = [ pytestEnv pkgs.poppler-utils ];
            }
            ''
              cp -r ${self} src
              chmod -R u+w src
              cd src
              ${pytestEnv}/bin/pytest -q tests
              touch $out
            '';
        }
      );
    };
}
