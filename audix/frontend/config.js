// Dirección de la API. Usa el mismo host desde el que se abrió la PWA,
// así funciona en la PC (localhost) y en el celular (IP de la PC en la red Wi-Fi).
const AUDIX_API = `${location.protocol}//${location.hostname}:8000`;
