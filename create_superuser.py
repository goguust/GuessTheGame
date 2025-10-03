from django.contrib.auth import get_user_model

User = get_user_model()

username = "admin"
email = "admin@example.com"
password = "password123"   # puoi cambiarla subito dopo dal pannello admin

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=email, password=password)
    print("Superuser creato con successo!")
else:
    print("Superuser già esistente, nessuna azione.")
