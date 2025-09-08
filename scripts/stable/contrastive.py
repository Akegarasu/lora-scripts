import torch

def contrastive_target(latents, noise, method='Random-Noise',
                      noise_strength=0.1):
    '''
    Generate Negative samples for contrastive learning.
    Args:
        latents: The input latent representations.
        noise: The input noise.
        method: The method used for generating negative samples.
        noise_strength: The strength of the noise applied.
    Returns:
        latents_neg: The negative latent representations.
        noise_neg: The negative noise.
    '''
    if method == 'Random-Noise' or latents.shape[0] == 1:
        latents_neg = latents + torch.randn_like(latents) * noise_strength
        noise_neg = noise + torch.randn_like(noise) * noise_strength
    elif method == 'Permutation':
        perm = torch.randperm(latents.shape[0])
        latents_neg = latents[perm]
        noise_neg = noise[perm]
    elif method == 'Random-index':
        idx = torch.randint(0, latents.shape[0], (latents.shape[0],))
        latents_neg = latents[idx]
        noise_neg = noise[idx]
    elif method == 'Circular':
        perm = torch.arange(latents.shape[0])
        perm = torch.roll(perm, shifts=1)
        latents_neg = latents[perm]
        noise_neg = noise[perm]
    elif method == 'Hard-Negative':
        sim = torch.cdist(latents, latents, p=2)    # 欧氏距离矩阵
        sim.fill_diagonal_(float('inf'))    # 忽略自身
        idx_hard = sim.argmin(dim=1)
        latents_neg = latents[idx_hard]
        noise_neg = noise[idx_hard]
    else:
        raise ValueError(f'Unknown method: {method}')
    return latents_neg, noise_neg
