"""Phase-free support-slip cost at the solver's reported world contact points."""
import torch
def contact_slip_cost(origins,velocities,angular,points,mask):
    r=points[:,:,None,:]-origins[:,None,:,:]
    v=velocities[:,None,:,:]+torch.cross(angular[:,None,:,:].expand_as(r),r,dim=-1)
    horizontal_sq=v[...,:2].square().sum(dim=-1)
    # Average multiple contact points of one foot before adding the four feet.
    per_foot=torch.where(mask,horizontal_sq,0.).sum(dim=1)/mask.sum(dim=1).clamp(min=1)
    return per_foot.sum(dim=1)
