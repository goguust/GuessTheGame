from django.db import models


class Inmate(models.Model):
    booking_number = models.CharField(max_length=20, unique=True)
    first_name     = models.CharField(max_length=100, blank=True)
    last_name      = models.CharField(max_length=100, blank=True)
    age            = models.IntegerField(blank=True, null=True)
    #image          = models.ImageField(upload_to="inmates/", blank=True, null=True)

    def __str__(self):
        return f"{self.last_name}, {self.first_name} ({self.booking_number})"


class Charge(models.Model):
    inmate             = models.ForeignKey(Inmate, on_delete=models.CASCADE, related_name="charges")
    charge             = models.TextField()
    bond_amount        = models.CharField(max_length=50, blank=True)        # opzionale
    court_case_number  = models.CharField(max_length=50, blank=True)        # opzionale
    court_location     = models.CharField(max_length=50, blank=True)        # opzionale
    note               = models.TextField(blank=True)                       # opzionale

    def __str__(self):
        return f"{self.charge[:60]}..."

class ChildAbuseIndex(models.Model):
    inmate = models.OneToOneField("Inmate", on_delete=models.CASCADE, related_name="idx_child_abuse")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"ChildAbuseIndex({self.inmate.booking_number})"


class NonChildAbuseIndex(models.Model):
    inmate = models.OneToOneField("Inmate", on_delete=models.CASCADE, related_name="idx_non_child_abuse")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"NonChildAbuseIndex({self.inmate.booking_number})"

class LeaderboardEntry(models.Model):
    MODES = (
        ("child", "Child Abuse"),
        ("murder", "Murder"),
        ("drugs", "Drugs"),
    )
    name  = models.CharField(max_length=50)
    score = models.IntegerField()
    mode = models.CharField(max_length=20, choices=MODES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score", "created_at"]

    def __str__(self):
        return f"[{self.mode}] {self.name} — {self.score}"

class MurderIndex(models.Model):
    inmate = models.OneToOneField("Inmate", on_delete=models.CASCADE, related_name="idx_murder")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"MurderIndex({self.inmate.booking_number})"


class NonMurderIndex(models.Model):
    inmate = models.OneToOneField("Inmate", on_delete=models.CASCADE, related_name="idx_non_murder")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"NonMurderIndex({self.inmate.booking_number})"

class CannabisIndex(models.Model):
    inmate = models.OneToOneField("Inmate", on_delete=models.CASCADE, related_name="idx_cannabis")

class CocaineFentanylIndex(models.Model):
    inmate = models.OneToOneField("Inmate", on_delete=models.CASCADE, related_name="idx_cocaine_fentanyl")
