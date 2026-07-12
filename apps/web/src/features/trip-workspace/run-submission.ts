import type { RunCreateInput, TripRequestInput } from "@/shared/api/types";

export function buildPlanConversionCommand(question?: string): string {
  const cleanQuestion = question?.trim();
  return cleanQuestion
    ? `请将这个旅行问题转成一份真实、可执行并带证据的逐日方案：${cleanQuestion}`
    : "请将当前旅行问答转成一份真实、可执行并带证据的逐日方案。";
}

export function buildQuestionRunInput(
  message: string,
  title: string,
  destinationHint?: string,
): RunCreateInput {
  return {
    command: {
      type: "trip.ask",
      message: message.trim(),
      payload: {
        title: title.trim(),
        locale: "zh-CN",
        ...(destinationHint?.trim() ? { destination_hint: destinationHint.trim() } : {}),
      },
    },
    base_artifact_id: null,
    base_artifact_version: null,
  };
}

export function buildPlanningRunInput(
  message: string,
  title: string,
  baseArtifactId: string | null,
  baseArtifactVersion: number | null,
  tripRequest: TripRequestInput,
): RunCreateInput {
  const replan = !!baseArtifactId && !!baseArtifactVersion;
  return {
    command: {
      type: replan ? "trip.replan" : "trip.plan",
      message: message.trim(),
      payload: {
        title: title.trim(),
        ...(replan
          ? {
              patch: {
                dates: {
                  start_date: tripRequest.start_date,
                  end_date: tripRequest.end_date,
                },
                budget: {
                  min_amount: tripRequest.budget_min,
                  max_amount: tripRequest.budget_max,
                  currency: tripRequest.currency,
                },
                preferences: { add: [...tripRequest.preferences], remove: [] },
              },
            }
          : {
              trip_request: {
                ...tripRequest,
                preferences: [...tripRequest.preferences],
                accessibility_needs: [...tripRequest.accessibility_needs],
              },
            }),
      },
    },
    base_artifact_id: replan ? baseArtifactId : null,
    base_artifact_version: baseArtifactVersion,
  };
}
