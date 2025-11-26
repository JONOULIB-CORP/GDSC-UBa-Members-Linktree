-- random_image.lua
-- Script pour wrk2 qui remplace 'image=...' dans l'URL par une image
-- choisie aléatoirement dans la liste ci-dessous à chaque requête.

-- La liste des images doit correspondre à la section PAYLOADS du script Python.
local images = {
  "tiny.jpg",
  "small.jpg",
  "large.jpg"
}

-- La fonction request() est appelée par wrk2 avant chaque requête.
request = function()
  -- Choisir un nom d'image aléatoire dans la table
  local image_name = images[math.random(#images)]

  -- Remplacer le paramètre 'image' dans le chemin de la requête.
  -- Utilise une expression régulière simple pour trouver et remplacer.
  local new_path = string.gsub(wrk.path, "image=[^&]+", "image=" .. image_name)

  return wrk.format(nil, new_path)
end
