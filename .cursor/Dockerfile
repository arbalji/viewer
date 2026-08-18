# PHP is baked into the image from AWS ECR Public (an already-allowlisted
# registry) so no per-session apt/mirror install is required. process.php only
# uses file_get_contents(), so the base php-cli image is sufficient.
FROM public.ecr.aws/docker/library/php:8.3-cli-bookworm

ENV DEBIAN_FRONTEND=noninteractive

# insert_userscripts.py needs Python 3 (standard library only). git/curl are
# installed for a fully custom image per Cloud Agent guidance.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
