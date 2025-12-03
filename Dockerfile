# Utiliser l'image Python officielle
FROM python:3.11-slim

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers de dépendances
COPY requirements.txt .

# Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY main.py .

# Exposer le port (Cloud Run utilise la variable PORT)
EXPOSE 8080

# Commande de démarrage
CMD ["python", "main.py"]
