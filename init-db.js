// Initialisation de la base de données MongoDB pour l'architecture microservices

// Connexion à la base d'identité
db = db.getSiblingDB('identity_db');
db.createCollection('users');
db.users.createIndex({ "email": 1 }, { unique: true });

// Insertion d'un admin par défaut si nécessaire
db.users.insertOne({
  email: "admin@radiology.com",
  password_hash: "$2a$10$xV.Z8Q6w9D6hYFhGf.o6ee8vYXG6o8o6vYXG6o8o6vYXG6o8o6vYXG", // Exemple de hash BCrypt
  full_name: "Super Admin",
  role: "ADMIN",
  created_at: new Date()
});

// Connexion à la base de cours
db = db.getSiblingDB('course_db');
db.createCollection('courses');
db.createCollection('documents');

print("✅ MongoDB Initialized: identity_db and course_db created with collections.");
