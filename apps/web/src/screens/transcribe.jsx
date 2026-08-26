import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { Check, LoaderCircle, Pause, Play, Search, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { JobProgress } from "@/components/job-progress";
import { ProjectSteps } from "@/components/project-steps";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select } from "@/components/ui/select";
import { useProject } from "@/hooks/use-project";
import { api } from "@/lib/api";
import { showError, useApp } from "@/lib/app-context";

export function TranscribeScreen() {
  const { project, loading } = useProject();
  const {
    providers,
    voiceCatalog,
    job,
    setJob,
    jobActive,
    busy,
    setBusy,
  } = useApp();
  const [transcriptionProvider, setTranscriptionProvider] = useState("");
  const [cleanupProvider, setCleanupProvider] = useState("");
  const [ttsVoice, setTtsVoice] = useState("");
  const [voiceSearch, setVoiceSearch] = useState("");
  const [playingVoice, setPlayingVoice] = useState(null);
  const sampleAudio = useRef(null);

  useEffect(() => {
    if (!transcriptionProvider) {
      const selected =
        providers.transcription.find(
          (provider) => provider.default && provider.configured,
        ) || providers.transcription.find((provider) => provider.configured);
      if (selected) setTranscriptionProvider(selected.id);
    }
    if (!cleanupProvider) {
      const selected = providers.cleanup.find((provider) => provider.configured);
      if (selected) setCleanupProvider(selected.id);
    }
  }, [providers, transcriptionProvider, cleanupProvider]);

  useEffect(() => {
    if (!ttsVoice && voiceCatalog.voices.length) {
      const preferred = project?.tts_voice || voiceCatalog.default_voice;
      const exists = voiceCatalog.voices.some((voice) => voice.id === preferred);
      setTtsVoice(exists ? preferred : voiceCatalog.voices[0].id);
    }
  }, [project?.tts_voice, ttsVoice, voiceCatalog]);

  useEffect(
    () => () => {
      sampleAudio.current?.pause();
    },
    [],
  );

  const filteredVoices = useMemo(() => {
    const query = voiceSearch.trim().toLowerCase();
    if (!query) return voiceCatalog.voices;
    return voiceCatalog.voices.filter((voice) =>
      [voice.name, voice.id, voice.gender, voice.language].some((value) =>
        value.toLowerCase().includes(query),
      ),
    );
  }, [voiceCatalog.voices, voiceSearch]);

  if (loading && !project) return <LoadingCard />;
  if (!project) return <Navigate to="/projects" replace />;
  if (project.transcript_cues?.length && !jobActive) {
    return <Navigate to={`/projects/${project.project_id}/transcript`} replace />;
  }

  const selectedTranscription = providers.transcription.find(
    (provider) => provider.id === transcriptionProvider,
  );
  const selectedCleanup = providers.cleanup.find(
    (provider) => provider.id === cleanupProvider,
  );
  const ready =
    selectedTranscription?.configured && selectedCleanup?.configured && ttsVoice;
  const currentJob = job?.project_id === project.project_id ? job : null;

  function toggleVoiceSample(voice) {
    if (playingVoice === voice.id) {
      sampleAudio.current?.pause();
      sampleAudio.current = null;
      setPlayingVoice(null);
      return;
    }
    sampleAudio.current?.pause();
    const audio = new Audio(voice.sample_url);
    sampleAudio.current = audio;
    setPlayingVoice(voice.id);
    audio.addEventListener("ended", () => setPlayingVoice(null), { once: true });
    audio.play().catch((reason) => {
      setPlayingVoice(null);
      showError(reason, `voice-sample-${voice.id}`);
    });
  }

  async function startTranscription() {
    if (busy || jobActive || !ready) return;
    setBusy(true);
    try {
      const next = await api.transcribe(project.project_id, {
        transcription_provider: transcriptionProvider,
        cleanup_provider: cleanupProvider,
        tts_voice: ttsVoice,
      });
      setJob(next);
      toast.info("Transcription started", { id: `job-${next.id}` });
    } catch (reason) {
      showError(reason, "start-transcription");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mx-auto max-w-5xl">
      <ProjectSteps project={project} active="transcribe" />
      <div className="mb-6">
        <h1 className="font-display text-3xl font-bold">Transcribe</h1>
        <p className="mt-1 text-muted-foreground">{project.title}</p>
      </div>
      <div className="grid gap-5">
        {currentJob && <JobProgress job={currentJob} />}
        <Card>
          <h2 className="font-display text-xl font-bold">
            Speech recognition and cleanup
          </h2>
          <p className="mb-5 mt-1 text-sm text-muted-foreground">
            These settings lock once processing starts.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Select
              label="Transcription"
              value={transcriptionProvider}
              onValueChange={setTranscriptionProvider}
              options={providers.transcription.map((item) => ({
                ...item,
                label: `${item.label}${item.configured ? "" : " · unavailable"}`,
                disabled: !item.configured,
              }))}
              disabled={jobActive || busy}
            />
            <Select
              label="Cleanup model"
              value={cleanupProvider}
              onValueChange={setCleanupProvider}
              options={providers.cleanup.map((item) => ({
                ...item,
                label: `${item.label}${item.configured ? "" : " · key needed"}`,
                disabled: !item.configured,
              }))}
              disabled={jobActive || busy}
            />
          </div>
        </Card>

        <Card>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="font-display text-xl font-bold">Narration voice</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Preview the same phrase, then select a voice for the entire project.
              </p>
            </div>
            <span className="text-sm text-muted-foreground">
              {voiceCatalog.voices.length} English voices
            </span>
          </div>
          <label className="relative mt-4 block">
            <span className="sr-only">Search voices</span>
            <Search
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
              size={16}
            />
            <Input
              className="pl-9"
              value={voiceSearch}
              onChange={(event) => setVoiceSearch(event.target.value)}
              placeholder="Search by name, language, or gender"
              disabled={jobActive || busy}
            />
          </label>
          <ScrollArea className="mt-4 h-96 rounded-xl border border-border">
            <div className="grid gap-2 p-3 sm:grid-cols-2">
              {filteredVoices.map((voice) => {
                const selected = voice.id === ttsVoice;
                const playing = voice.id === playingVoice;
                return (
                  <div
                    key={voice.id}
                    role="radio"
                    aria-checked={selected}
                    tabIndex={jobActive || busy ? -1 : 0}
                    onClick={() => {
                      if (!jobActive && !busy) setTtsVoice(voice.id);
                    }}
                    onKeyDown={(event) => {
                      if (
                        !jobActive &&
                        !busy &&
                        ["Enter", " "].includes(event.key)
                      ) {
                        event.preventDefault();
                        setTtsVoice(voice.id);
                      }
                    }}
                    className={`flex cursor-pointer items-center gap-3 rounded-xl border p-2.5 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                      selected
                        ? "border-primary bg-primary/5"
                        : "border-border bg-background hover:bg-muted/50"
                    }`}
                  >
                    <Button
                      size="icon"
                      variant="outline"
                      className="h-8 w-8"
                      onClick={(event) => {
                        event.stopPropagation();
                        toggleVoiceSample(voice);
                      }}
                      disabled={!voice.sample_available}
                      aria-label={`${playing ? "Pause" : "Play"} ${voice.name} sample`}
                      title={`${playing ? "Pause" : "Play"} ${voice.name} sample`}
                    >
                      {playing ? <Pause size={14} /> : <Play size={14} />}
                    </Button>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold">{voice.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {voice.language} · {voice.gender}
                      </p>
                    </div>
                    {selected && <Check className="text-primary" size={17} />}
                  </div>
                );
              })}
              {filteredVoices.length === 0 && (
                <p className="p-5 text-center text-sm text-muted-foreground sm:col-span-2">
                  No voices match that search.
                </p>
              )}
            </div>
          </ScrollArea>
        </Card>
        <div>
          <Button
            size="lg"
            onClick={startTranscription}
            disabled={!ready || jobActive || busy}
          >
            {jobActive ? (
              <LoaderCircle className="animate-spin" size={17} />
            ) : (
              <Sparkles size={17} />
            )}
            {jobActive ? "Transcribing…" : "Start transcription"}
          </Button>
          {!ready && (
            <p className="mt-3 text-sm text-muted-foreground">
              Configure both processing providers and select a narration voice.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

function LoadingCard() {
  return (
    <Card className="grid min-h-64 place-items-center">
      <LoaderCircle className="animate-spin text-primary" />
    </Card>
  );
}
