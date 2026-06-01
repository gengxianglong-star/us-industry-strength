import { NavLink } from "react-router-dom";
import { NavIconBreadth, NavIconStrong } from "./NavIcons";

export function TopNav() {
  return (
    <nav className="top-nav" aria-label="Main navigation">
      <NavLink
        className={({ isActive }) => `top-nav-item${isActive ? " active" : ""}`}
        to="/breadth"
      >
        <NavIconBreadth />
        <span>Market Breadth</span>
      </NavLink>
      <NavLink
        className={({ isActive }) => `top-nav-item${isActive ? " active" : ""}`}
        to="/strong"
        end
      >
        <NavIconStrong />
        <span>Strong Industry</span>
      </NavLink>
    </nav>
  );
}
