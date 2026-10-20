//! Risoluzione sicura dei percorsi: tutto ciò che JARVIS tocca deve stare dentro la cartella home.
use std::path::{Component, Path, PathBuf};

const ALIASES: [(&str, &str); 7] = [
    ("documenti", "Documents"),
    ("scaricati", "Downloads"),
    ("download", "Downloads"),
    ("immagini", "Pictures"),
    ("scrivania", "Desktop"),
    ("musica", "Music"),
    ("video", "Videos"),
];

/// Trasforma l'input (relativo alla home o assoluto) in un percorso dentro `home`.
/// Rifiuta `..`, prefissi di unità diversi e qualunque percorso che esca dalla home.
pub fn resolve(home: &Path, input: &str) -> Result<PathBuf, String> {
    let input = input.trim().trim_matches('"');
    if input.is_empty() {
        return Err("percorso vuoto".into());
    }
    let given = Path::new(input);
    let rel: PathBuf = if given.is_absolute() {
        given
            .strip_prefix(home)
            .map_err(|_| "percorso fuori dalla cartella home".to_string())?
            .to_path_buf()
    } else {
        given.to_path_buf()
    };
    let mut out = home.to_path_buf();
    for (i, c) in rel.components().enumerate() {
        match c {
            Component::Normal(name) => {
                let name = name.to_string_lossy();
                let lower = name.to_lowercase();
                match ALIASES.iter().find(|(it, _)| i == 0 && *it == lower) {
                    Some((_, en)) => out.push(en),
                    None => out.push(&*name),
                }
            }
            Component::CurDir => {}
            _ => return Err("percorso non consentito".into()),
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn home() -> PathBuf {
        PathBuf::from(if cfg!(windows) { r"C:\Users\matteo" } else { "/home/matteo" })
    }

    #[test]
    fn relative_and_aliases() {
        assert_eq!(resolve(&home(), "Documenti/tasse.pdf").unwrap(), home().join("Documents").join("tasse.pdf"));
        assert_eq!(resolve(&home(), "progetti").unwrap(), home().join("progetti"));
        // l'alias vale solo come primo componente
        assert_eq!(resolve(&home(), "a/documenti").unwrap(), home().join("a").join("documenti"));
    }

    #[test]
    fn rejects_escapes() {
        assert!(resolve(&home(), "../altro").is_err());
        assert!(resolve(&home(), "a/../../b").is_err());
        assert!(resolve(&home(), "").is_err());
        let outside = if cfg!(windows) { r"C:\Windows\System32" } else { "/etc/passwd" };
        assert!(resolve(&home(), outside).is_err());
    }

    #[test]
    fn absolute_inside_home_is_ok() {
        let p = home().join("Desktop").join("x.txt");
        assert_eq!(resolve(&home(), p.to_str().unwrap()).unwrap(), p);
    }
}
