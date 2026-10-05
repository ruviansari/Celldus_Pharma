from django.db import models

class Contact(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=15)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Subscriber(models.Model):
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"


class Product(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    image = models.CharField(max_length=255, default='images/products/default.png')
    # New Fields 
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    size = models.CharField(max_length=100, blank=True, help_text="e.g. 10x10 Tablets, 100ml")
    stock = models.IntegerField(default=0)
    specification = models.TextField(blank=True, help_text="Detailed product specifications")
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Blog(models.Model):
    title = models.CharField(max_length=255)
    desc = models.TextField(help_text="Short excerpt")
    image = models.CharField(max_length=255, default='images/blog/blog-one-740x504.jpg')
    author = models.CharField(max_length=100, default='Admin')
    body = models.TextField(help_text="Full blog content (paragraphs separated by newline)")
    key_points = models.TextField(blank=True, help_text="Key takeaways (one per line)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def date(self):
        return self.created_at.strftime("%B %d, %Y")

    @property
    def content(self):
        return [p.strip() for p in (self.body or '').split('\n') if p.strip()]

    @property
    def points(self):
        return [p.strip() for p in (self.key_points or '').split('\n') if p.strip()]

