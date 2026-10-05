import ssl
from django.core.mail.backends.smtp import EmailBackend as SmtpBackend

class CustomEmailBackend(SmtpBackend):
    """
    Custom SMTP Email Backend that bypasses SSL/TLS certificate verification.
    Useful when the SMTP server uses self-signed certificates or has a hostname mismatch.
    """
    def open(self):
        if self.connection:
            return False
        connection_params = {}
        if self.timeout is not None:
            connection_params['timeout'] = self.timeout
            
        try:
            self.connection = self.connection_class(
                self.host,
                self.port,
                **connection_params
            )
            
            # Bypass SSL verification during STARTTLS
            if self.use_tls:
                context = ssl._create_unverified_context()
                self.connection.ehlo()
                self.connection.starttls(context=context)
                self.connection.ehlo()
                
            if self.username and self.password:
                self.connection.login(self.username, self.password)
                
            return True
        except Exception:
            if not self.fail_silently:
                raise
            return False
