#!/bin/bash
echo "Gerando JWT_SECRET_KEY..."
SECRET=$(openssl rand -hex 32)
echo "JWT_SECRET_KEY=$SECRET"
echo ""
echo "Copie a linha acima para o seu .env"
