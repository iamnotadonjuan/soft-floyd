import type { Messages } from "./en";

// Neutral Latin American Spanish, informal "tú". Typed as Messages so a
// missing or misshapen key fails `tsc` — keep keys in en.ts's order.
const es: Messages = {
  common: {
    language: "Idioma",
    back: "← Atrás",
    backToRides: "← Volver a tus salidas",
    next: "Siguiente",
    save: "Guardar",
    saving: "Guardando…",
    saved: "Guardado",
    loading: "Cargando…",
    noAppsYet: "Aún no hay apps disponibles.",
  },

  app: {
    serverError: (error) => `No se pudo conectar con el servidor: ${error}`,
    loading: "Cargando tu diario de salidas…",
  },

  rides: {
    titles: {
      road: "Salida en ruta", mtb: "Salida en montaña", indoor: "Salida en rodillo", other: "Salida",
    },
    fallbackTitle: "Salida",
    indoor: "Bajo techo",
    outdoor: "Al aire libre",
    climbing: (metres) => `${metres} m de ascenso`,
  },

  dashboard: {
    brand: "Soft Floyd / Diario de salidas",
    askCoach: "Pregúntale a tu coach",
    settings: "Ajustes",
    coachHint: "Conecta Garmin en Ajustes para activar a tu coach.",
    eyebrow: "Tu casa ciclista",
    title: "Pedalea con intención.",
    subtitle: "Tu objetivo, tu equipo y las salidas que de verdad registraste, en un solo lugar.",
    goalEyebrow: "Hacia dónde pedaleas",
    weeklySummary: (days, hours) =>
      `${days} ${days === 1 ? "día" : "días"} de salida · ${hours} ${hours === 1 ? "hora" : "horas"} por semana`,
    tierView: {
      power: "Vista con potencia y señales disponibles",
      hr: "Vista con frecuencia cardiaca",
      cadence: "Vista con cadencia",
      basic: "Vista básica con GPS",
    },
    connectionStatus: {
      connected: "Conectado",
      disconnected: "Sin conectar",
      reauth_required: "Vuelve a iniciar sesión",
      rate_limited: "Limitado temporalmente",
      error: "Requiere atención",
    },
    connectedApps: "Apps conectadas",
    connectionsAria: "Estado de las apps conectadas",
    connectionsError: (error) => `No se pudo cargar el estado de las conexiones: ${error}`,
    checkingConnections: "Revisando conexiones…",
    manageConnections: "Gestionar conexiones →",
    latestEyebrow: "Lo más reciente",
    newestRide: "Tu salida más reciente",
    loadingRides: "Cargando tus salidas…",
    emptyTitle: "Tu diario de salidas empieza aquí.",
    emptyBody: "Conecta Garmin en Ajustes para sincronizar tus salidas automáticamente. La primera conexión trae la actividad más reciente; las salidas anteriores de Garmin requieren una importación aparte.",
    connectGarmin: "Conectar Garmin",
    ridesError: (error) => `No se pudieron cargar las salidas: ${error}`,
    lookBack: "Mirar atrás",
    rideHistory: "Historial de salidas",
    loadingMore: "Cargando salidas…",
    showOlder: "Ver salidas anteriores",
    viewRide: "Ver salida →",
  },

  rideDetail: {
    loadError: (error) => `No se pudo cargar esta salida: ${error}`,
    loading: "Cargando salida…",
    recordedBy: (setting) => `Registrada por Garmin · ${setting}`,
    summaryAria: "Resumen de la salida",
    distance: "Distancia",
    duration: "Duración",
    elevationGain: "Desnivel positivo",
    avgHr: "Frecuencia cardiaca media",
    avgPower: "Potencia media",
    avgCadence: "Cadencia media",
    recordedHeading: "Qué registró esta salida",
    noSensors: "No se detectaron datos de sensores",
    onlyRecorded: "Solo las señales registradas aparecen arriba y en las vueltas de abajo.",
    fitUnavailable: "El archivo FIT no estaba disponible o no se pudo leer. La distancia, el tiempo y el desnivel vienen del resumen de Garmin; las lecturas de sensores no se pueden verificar para esta salida.",
    laps: "Vueltas",
    lap: (n) => `Vuelta ${n}`,
  },

  coach: {
    brand: "Soft Floyd / Coach",
    suggestions: [
      "¿Cómo me fue en el último mes de salidas?",
      "¿Qué debería trabajar para subir mejor?",
      "Planea mi próxima semana de entrenamiento según mi horario.",
    ],
    sourcesAria: "Fuentes de libros",
    sourcePages: (title, pages) => `${title}, pág. ${pages}`,
    sidebarAria: "Conversaciones y memoria",
    newConversation: "Nueva conversación",
    conversationsAria: "Conversaciones",
    noConversations: "Aún no hay conversaciones.",
    deleteConversation: (title) => `Eliminar la conversación ${title}`,
    memorySummary: (count) => `Lo que recuerda el coach (${count})`,
    memoryEmpty: "Nada por ahora. Cuéntale al coach sobre lesiones, horarios o preferencias y lo tendrá en cuenta.",
    forget: (text) => `Olvidar: ${text}`,
    chatAria: "Chat con el coach",
    eyebrow: "Tu coach de ciclismo",
    title: "Pregunta sobre tus salidas, tu entrenamiento o cómo ir más rápido.",
    intro: "El coach lee tus salidas sincronizadas y los libros de entrenamiento importados, y recuerda lo que le cuentas. Solo habla de ciclismo.",
    thinking: "Pensando…",
    turnError: "El coach no pudo responder. Inténtalo de nuevo.",
    messageLabel: "Escríbele al coach",
    placeholder: "Pregúntale a tu coach… (Shift+Enter para una nueva línea)",
    coaching: "Respondiendo…",
    send: "Enviar",
  },

  fields: {
    hoursPerWeek: "Horas por semana",
    birthYear: "Año de nacimiento",
    weightKg: "Peso (kg)",
    maxHr: "Frecuencia cardiaca máxima (ppm)",
    yearsRiding: "Años pedaleando",
    longestRide: "Salida más larga de los últimos meses (km)",
    describeYourself: "¿Cómo te describirías?",
    followedPlan: "Ya he seguido un plan de entrenamiento estructurado",
    healthNotes: "Algo que debamos saber: lesiones, limitaciones, etc.",
    ftp: "FTP (vatios)",
    lthr: "FC de umbral de lactato (ppm)",
    ownWords: "En tus propias palabras",
    eventName: "Nombre del evento",
  },

  levels: {
    beginner: "Estoy empezando",
    recreational: "Recreativo",
    enthusiast: "Entusiasta",
    competitive: "Competitivo / carreras",
  },

  focus: {
    endurance: "Rodar más tiempo sin desfallecer",
    climbing: "Subir mejor",
    flat_speed: "Ir más rápido en el plano",
    sprint: "Sprint / esfuerzos cortos e intensos",
    technical_skill: "Manejo de la bici y técnica",
    weight: "Bajar de peso",
    first_event: "Terminar mi primer evento",
    consistency: "Salir a rodar con más constancia",
    enjoy: "Disfrutarlo más, con menos presión",
  },

  availability: {
    days: {
      mon: "Lun", tue: "Mar", wed: "Mié", thu: "Jue", fri: "Vie", sat: "Sáb", sun: "Dom",
    },
    whichDays: "¿Qué días sueles salir a rodar?",
    selectDays: "Selecciona tus días habituales de salida.",
    daysPerWeek: (n) => `${n} ${n === 1 ? "día" : "días"} por semana`,
    weekdayMax: "Máx. minutos por día entre semana",
    weekdayHint: "Para cada día de salida seleccionado de lunes a viernes.",
    weekendMax: "Máx. minutos por día de fin de semana",
  },

  onboarding: {
    brand: "Soft Floyd / Primeros pasos",
    tagline: "Un poco de contexto hace un mejor coaching.",
    eyebrow: "Tu punto de partida",
    title: "Conozcamos cómo pedaleas.",
    stepOf: (step, total) => `Paso ${step} de ${total}`,
    progressAria: "Progreso de la configuración",
    saveError: (error) => `No se pudo guardar: ${error}`,
    savingAnswers: "Guardando tus respuestas…",
    readyEyebrow: "Listo para rodar",
    readyTitle: "Todo está listo.",
    readyBody: "Esto es lo que puedo usar para entender tus salidas:",
    goToDashboard: "Ir al inicio",
    habits: {
      title: "¿Cómo pedaleas ahora?",
      body: "Con números aproximados basta; los afinaremos después con tus salidas reales.",
    },
    goals: {
      title: "¿En qué quieres mejorar?",
      body: "Elige todo lo que aplique; esto define cómo el coach enfoca todo lo demás.",
      goalPlaceholder: "p. ej., subir mejor para un gran fondo que se acerca",
      eventQuestion: "¿Tienes algún evento en mente? (opcional)",
    },
    garage: {
      title: "¿En qué pedaleas?",
      body: "Agrega cada bici que de verdad usas; los sensores cambian de una bici a otra, así que preguntamos por cada una. Un rodillo también cuenta como bici.",
    },
    about: {
      title: "Un poco sobre ti",
      body: "Todo es opcional; omite lo que prefieras no responder.",
      hrMonitor: "Uso un monitor de frecuencia cardiaca cuando pedaleo",
    },
    anchors: {
      title: "Un par de números de referencia",
      body: "Omite cualquiera si todavía no lo sabes.",
      ftpPlaceholder: "p. ej., 240",
      lthrDefault: "165 por defecto si no estás seguro.",
    },
    connect: {
      title: "Conecta tus apps",
      body: "Vincula Garmin para que tus salidas se sincronicen automáticamente. Siempre puedes hacerlo después desde Ajustes.",
    },
  },

  settings: {
    brand: "Soft Floyd / Tu configuración",
    eyebrow: "Un coach que conoce tu contexto",
    title: "Tu configuración de ciclista.",
    intro: "Cambia cualquier parte a medida que evolucionen tus objetivos, tu horario o tu equipo. Cada sección se guarda por separado.",
    habits: { title: "Hábitos", description: "Cuánto y cuándo pedaleas." },
    goals: { title: "Objetivos", description: "Para qué estás entrenando." },
    garage: { title: "Garaje", description: "Tus bicis y los sensores que lleva cada una." },
    about: { title: "Sobre ti", description: "Cuerpo y experiencia; todo es opcional." },
    anchors: {
      title: "Frecuencia cardiaca y referencias",
      description: "Los sensores de potencia, cadencia y velocidad se configuran por bici en el garaje de arriba.",
    },
    connections: { title: "Apps conectadas", description: "Trae tus salidas registradas a Soft Floyd." },
    hrMonitor: "Uso un monitor de frecuencia cardiaca",
  },

  bikes: {
    kinds: {
      road: "Ruta", gravel: "Gravel", mtb: "Montaña", tt: "CRI / triatlón", indoor: "Rodillo",
    },
    loadError: (error) => `No se pudieron cargar las bicis: ${error}`,
    loading: "Cargando tu garaje…",
    nicknameAria: (kind) => `Apodo de la bici de ${kind.toLowerCase()}`,
    powerMeter: "Potenciómetro",
    cadence: "Cadencia",
    speed: "Velocidad",
    primary: "Bici principal",
    makePrimary: "Hacer principal",
    remove: "Quitar",
  },

  capability: {
    power: (hasHr) =>
      `Tu garaje incluye un potenciómetro${hasHr ? " y usas un monitor de frecuencia cardiaca" : ""}. Solo usaré esas señales en las salidas donde Garmin realmente las registró.`,
    hr: "Pedaleas con monitor de frecuencia cardiaca. Usaré la frecuencia cardiaca en las salidas donde se registró, junto con el tiempo, la distancia y el desnivel.",
    cadence: (hasCadence) =>
      `Tu garaje incluye ${hasCadence ? "un sensor de cadencia" : "un sensor de velocidad"}. Trabajaré con las señales registradas en cada salida, además del tiempo, la distancia y el desnivel.`,
    basic: "Con tu equipo actual puedo usar el tiempo, la distancia y el desnivel de cada salida. No voy a inventar lecturas de frecuencia cardiaca ni de potencia.",
    tierLabel: {
      power: "potencia", hr: "frecuencia cardiaca", cadence: "cadencia", basic: "solo GPS",
    },
    bikeLine: (name, tier, primary) =>
      `${name}: se lee con ${tier}${primary ? " (principal)" : ""}`,
  },

  connections: {
    status: {
      connected: "Conectado",
      disconnected: "Sin conectar",
      reauth_required: "Debes iniciar sesión de nuevo",
      rate_limited: "Límite alcanzado; inténtalo pronto",
      error: "Error",
    },
    lastChecked: (when) => `Última revisión: ${when}`,
    disconnect: "Desconectar",
    loadError: (error) => `No se pudieron cargar las apps conectadas: ${error}`,
    loading: "Cargando apps conectadas…",
    garmin: {
      codePrompt: "Ingresa el código que Garmin te acaba de enviar",
      codeAria: "Código de verificación de Garmin",
      verifying: "Verificando…",
      verify: "Verificar",
      email: "Correo de Garmin",
      password: "Contraseña",
      passwordPlaceholder: "Contraseña de Garmin",
      connecting: "Conectando…",
      connect: "Conectar Garmin",
      privacy: "Tu contraseña solo va a tu servidor local de Soft Floyd para este inicio de sesión.",
    },
  },
};

export default es;
