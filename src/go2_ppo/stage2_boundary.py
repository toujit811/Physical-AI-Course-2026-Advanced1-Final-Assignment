"""Finite terminal reward queries without extending the physical terrain."""
import torch
def query_points(points,bounds):
    if not torch.isfinite(points).all():raise FloatingPointError("Nonfinite physical query position")
    xmin,xmax,ymin,ymax=bounds
    outside=((points[...,0]<xmin)|(points[...,0]>xmax)|(points[...,1]<ymin)|(points[...,1]>ymax)).any(dim=-1)
    bounded=points.clone()
    bounded[...,0].clamp_(xmin,xmax);bounded[...,1].clamp_(ymin,ymax)
    return bounded,outside
