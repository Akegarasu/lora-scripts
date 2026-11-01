// MOSS uses its own Euler/CFG sampler; match its upstream preview defaults.
export function sampleDefaults(trainerId: string) {
  return trainerId === 'moss_image.lora'
    ? { steps: 50, cfgScale: 3 }
    : { steps: 20, cfgScale: 1 }
}
